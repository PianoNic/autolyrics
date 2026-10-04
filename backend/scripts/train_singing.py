"""Fine-tune the singing acoustic model on songs with hand-made word timing.

    python scripts/train_singing.py prepare [training_dir]     # vocals + training windows
    python scripts/train_singing.py train [training_dir] [epochs]
    python scripts/train_singing.py install                     # use the result

`prepare` separates each song's vocals (one RoFormer pass) and cuts the song into windows of a
few seconds along its hand-made word timing, each with the phonemes of its words. `train`
continues the model's own CTC training from its current weights on those windows and keeps the
checkpoint with the lowest loss on held-out songs. `install` copies it to models/singing, where
the aligner picks it up (the original stays as checkpoint_Baseline.orig).

The benchmark songs are never part of the training set (collect_benchmark.py skips them), so
benchmark_suite.py measures the result on unseen songs.
"""

import json
import random
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from autolyrics.composition.container import Container
from autolyrics.domain.lyrics import Lyrics, Word
from autolyrics.infrastructure.ml.singing.lam_model import (
    BLANK,
    PHONE_ID,
    SPACE,
    UNKNOWN,
    Phonemizer,
    SingingPhonemeModel,
    build_network,
)
from autolyrics.infrastructure.runtime.background_priority import BackgroundPriority

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_RATE = SingingPhonemeModel.sample_rate
WINDOW = 8.0  # seconds of audio per training example (at most)
PAD = 0.3  # seconds of audio kept around a window's words


class TrainingSet:
    """Songs in `<root>/<slug>/` (source audio, truth.ttml, meta.json) turned into examples."""

    def __init__(self, root: Path, container: Container):
        self._root = root
        self._container = container
        self._phonemizer = Phonemizer()

    def songs(self) -> list[Path]:
        return sorted(p for p in self._root.iterdir() if (p / "meta.json").exists())

    def prepare(self) -> None:
        separator = self._container.separator
        for folder in self.songs():
            out = folder / "windows.npz"
            if out.exists():
                continue
            started = time.time()
            try:
                meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
                lyrics = self._container.ttml.parse((folder / "truth.ttml").read_text(
                    encoding="utf-8"))
                language = self._container.languages.guess(lyrics) or "en"
                if not self._phonemizer.supports(language):
                    print(f"{folder.name:40s} skipped ({language})", flush=True)
                    (folder / "skip").write_text(language)
                    continue
                vocals = separator.vocals_only(folder / meta["audio"], folder)
                samples = self._samples(vocals, folder)
                windows = self._windows(lyrics, language, samples)
                np.savez_compressed(out, **{f"audio{i}": a for i, (a, _) in enumerate(windows)},
                                    **{f"target{i}": t for i, (_, t) in enumerate(windows)})
                print(f"{folder.name:40s} {len(windows):3d} windows  {time.time() - started:.0f}s",
                      flush=True)
            except Exception as error:  # noqa: BLE001 - one bad song must not stop the rest
                print(f"{folder.name:40s} failed: {error}", flush=True)

    def _samples(self, vocals: Path, folder: Path) -> np.ndarray:
        mono = folder / f"vocals.{SAMPLE_RATE}.wav"
        if not mono.exists():
            self._container.ffmpeg.to_wav(vocals, mono, sample_rate=SAMPLE_RATE, mono=True)
        data, _ = sf.read(mono, dtype="float32")
        return data

    def _windows(self, lyrics: Lyrics, language: str, samples: np.ndarray):
        words = [w for line in lyrics.content_lines for w in self._whole(line.words) if w.timed]
        phones = self._phonemizer.phones([self._clean(w.text) or "a" for w in words], language)
        windows, current = [], []
        for word, ph in zip(words, phones, strict=True):
            if current and word.end - current[0][0].begin > WINDOW - 2 * PAD:
                windows.append(self._window(current, samples))
                current = []
            if ph and self._clean(word.text):
                current.append((word, ph))
        if current:
            windows.append(self._window(current, samples))
        return [w for w in windows if w is not None]

    @staticmethod
    def _window(items, samples: np.ndarray):
        start = max(0.0, items[0][0].begin - PAD)
        end = items[-1][0].end + PAD
        audio = samples[int(start * SAMPLE_RATE):int(end * SAMPLE_RATE)]
        target = []
        for k, (_, ph) in enumerate(items):
            if k:
                target.append(SPACE)
            target += [PHONE_ID.get(p, UNKNOWN) for p in ph]
        frames = len(audio) / SAMPLE_RATE / SingingPhonemeModel.FRAME_SECONDS
        if len(audio) < SAMPLE_RATE or frames < 2 * len(target):
            return None
        return audio.astype(np.float32), np.array(target, dtype=np.int16)

    @staticmethod
    def _whole(words: list[Word]) -> list[Word]:
        out, pieces = [], []
        for i, w in enumerate(words):
            pieces.append(w)
            if w.text.endswith(" ") or i == len(words) - 1:
                timed = [p for p in pieces if p.timed]
                out.append(Word(text="".join(p.text for p in pieces).strip(),
                                begin=timed[0].begin if timed else None,
                                end=timed[-1].end if timed else None))
                pieces = []
        return out

    @staticmethod
    def _clean(text: str) -> str:
        return "".join(ch for ch in text.lower() if ch.isalnum() or ch == "'").strip("'")

    def load(self) -> list[tuple[str, np.ndarray, np.ndarray]]:
        examples = []
        for folder in self.songs():
            out = folder / "windows.npz"
            if not out.exists():
                continue
            data = np.load(out)
            count = len([k for k in data.files if k.startswith("audio")])
            examples += [(folder.name, data[f"audio{i}"], data[f"target{i}"])
                         for i in range(count)]
        return examples


class Trainer:
    """CTC fine-tuning of the vendored network. Its last two LSTMs see each frame on its own at
    inference (batch 1 with batch_first=False); training reproduces exactly that by running them
    over the flattened (batch x time) frames, so the trained model behaves as it will be used."""

    def __init__(self, checkpoint: Path, device: str = "cuda"):
        import torch
        import torchaudio

        self.torch = torch
        self.device = device
        self.network = build_network()
        state = torch.load(checkpoint, map_location="cpu", weights_only=False)
        self.network.load_state_dict(state["model_state_dict"])
        self.network.to(device)
        self.mel = torchaudio.transforms.MelSpectrogram(
            sample_rate=SAMPLE_RATE, n_mels=128, n_fft=512).to(device)

    def forward(self, audio):  # audio: (batch, samples), zero-padded
        torch = self.torch
        net = self.network
        x = self.mel(audio)[:, None]  # (B, 1, 128, T)
        x = net.maxpooling(net.rescnn_layers(net.cnn_layers(x)))
        b, c, f, t = x.size()
        x = net.fully_connected(x.view(b, c * f, t).transpose(1, 2))  # (B, T, F)
        first, second, third = net.bilstm
        x = first(x)
        flat = x.reshape(1, b * t, x.shape[-1])  # every frame on its own, as at inference
        flat = third(second(flat))
        x = flat.reshape(b, t, -1)
        return torch.log_softmax(net.classifier(x), dim=2)

    def batches(self, examples, size: int, shuffle: bool):
        order = list(range(len(examples)))
        if shuffle:
            random.shuffle(order)
        for i in range(0, len(order), size):
            yield [examples[k] for k in order[i:i + size]]

    def loss(self, batch):
        torch = self.torch
        longest = max(len(a) for _, a, _ in batch)
        audio = torch.zeros(len(batch), longest)
        for i, (_, a, _) in enumerate(batch):
            audio[i, :len(a)] = torch.from_numpy(a)
        logp = self.forward(audio.to(self.device))  # (B, T, C)
        lengths = torch.tensor([min(logp.shape[1], int(len(a) / 256) // 3)
                                for _, a, _ in batch])
        targets = torch.cat([torch.from_numpy(t.astype(np.int64)) for _, _, t in batch])
        target_lengths = torch.tensor([len(t) for _, _, t in batch])
        return torch.nn.functional.ctc_loss(logp.transpose(0, 1), targets, lengths,
                                            target_lengths, blank=BLANK, zero_infinity=True)

    def train(self, examples, epochs: int, out: Path, lr: float = 5e-5, batch: int = 16):
        torch = self.torch
        songs = sorted({s for s, _, _ in examples})
        random.Random(7).shuffle(songs)
        held = set(songs[:max(1, len(songs) // 20)])
        train = [e for e in examples if e[0] not in held]
        valid = [e for e in examples if e[0] in held]
        print(f"{len(train)} training windows from {len(songs) - len(held)} songs, "
              f"{len(valid)} held-out windows from {len(held)} songs", flush=True)
        optimizer = torch.optim.AdamW(self.network.parameters(), lr=lr, weight_decay=1e-4)
        best = self.validate(valid)
        print(f"before: held-out loss {best:.4f}", flush=True)
        self.save(out)
        for epoch in range(1, epochs + 1):
            self.network.train()
            started, total, steps = time.time(), 0.0, 0
            for group in self.batches(train, batch, shuffle=True):
                loss = self.loss(group)
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.network.parameters(), 5.0)
                optimizer.step()
                total += float(loss)
                steps += 1
            held_out = self.validate(valid)
            mark = ""
            if held_out < best:
                best, mark = held_out, "  (saved)"
                self.save(out)
            print(f"epoch {epoch}: train {total / max(1, steps):.4f}  held-out {held_out:.4f}  "
                  f"{time.time() - started:.0f}s{mark}", flush=True)

    def validate(self, examples) -> float:
        torch = self.torch
        self.network.eval()
        losses = []
        with torch.no_grad():
            for group in self.batches(examples, 16, shuffle=False):
                losses.append(float(self.loss(group)))
        return float(np.mean(losses)) if losses else float("inf")

    def save(self, out: Path) -> None:
        self.torch.save({"model_state_dict": self.network.state_dict()}, out)


def main() -> None:
    BackgroundPriority().apply()
    command = sys.argv[1] if len(sys.argv) > 1 else "train"
    root = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "training"
    container = Container()
    singing = container.model_files.singing_checkpoint()
    tuned = singing.with_name("checkpoint_finetuned")
    if command == "prepare":
        TrainingSet(root, container).prepare()
    elif command == "train":
        epochs = int(sys.argv[3]) if len(sys.argv) > 3 else 6
        examples = TrainingSet(root, container).load()
        Trainer(singing).train(examples, epochs, tuned)
    elif command == "install":
        original = singing.with_name("checkpoint_Baseline.orig")
        if not original.exists():
            shutil.copyfile(singing, original)
        shutil.copyfile(tuned, singing)
        for cache in ROOT.glob("benchmarks/*/*/*.singing-phonemes.npz"):
            cache.unlink()  # emissions of the old model
        print(f"installed {tuned.name}; original kept as {original.name}")


if __name__ == "__main__":
    main()
