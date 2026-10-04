"""The phoneme acoustic model of LyricsAlignment-Multilingual (Huang & Benetos, ISMIR 2025 LBD;
MIT license, https://github.com/jhuang448/LyricsAlignment-Multilingual). Trained on sung
vocals from DALI, separated as we separate ours, so held notes and melisma are what it knows.
The network is vendored as published, including its quirks (the last two LSTMs run with
batch_first=False, which the trained weights depend on)."""

import logging
from pathlib import Path
from typing import ClassVar

import numpy as np

from autolyrics.infrastructure.services.ml.singing.acoustic import Emissions, IAcousticModel

log = logging.getLogger(__name__)

PHONES = ['a', 'aɪ', 'aʊ', 'b', 'd', 'dʒ', 'e', 'ee', 'eɪ', 'eː', 'f', 'h', 'i', 'iː', 'j',
          'k', 'l', 'm', 'n', 'o', 'oʊ', 'oː', 'p', 'r', 's', 'ss', 't', 'ts', 'tʃ', 'tː',
          'u', 'uː', 'v', 'w', 'x', 'y', 'z', 'æ', 'ç', 'ð', 'ŋ', 'ɐ', 'ɑː', 'ɑːɹ', 'ɑ̃',
          'ɔ', 'ɔː', 'ɔ̃', 'ə', 'ɚ', 'ɛ', 'ɛ̃', 'ɜ', 'ɜː', 'ɡ', 'ɣ', 'ɪ', 'ɲ', 'ɹ', 'ɾ', 'ʁ',
          'ʃ', 'ʊ', 'ʊɹ', 'ʌ', 'ʒ', 'ʝ', 'β', 'θ', ' ']
PHONE_ID = {p: i for i, p in enumerate(PHONES)}
SPACE, UNKNOWN, BLANK = 69, 70, 71


def build_network():
    import torch.nn.functional as F
    from torch import nn

    class CNNLayerNorm(nn.Module):
        def __init__(self, n_feats):
            super().__init__()
            self.layer_norm = nn.LayerNorm(n_feats)

        def forward(self, x):
            x = x.transpose(2, 3).contiguous()
            x = self.layer_norm(x)
            return x.transpose(2, 3).contiguous()

    class ResidualCNN(nn.Module):
        def __init__(self, in_channels, out_channels, kernel, stride, dropout, n_feats):
            super().__init__()
            self.cnn1 = nn.Conv2d(in_channels, out_channels, kernel, stride, padding=kernel // 2)
            self.cnn2 = nn.Conv2d(out_channels, out_channels, kernel, stride,
                                  padding=kernel // 2)
            self.dropout1 = nn.Dropout(dropout)
            self.dropout2 = nn.Dropout(dropout)
            self.layer_norm1 = CNNLayerNorm(n_feats)
            self.layer_norm2 = CNNLayerNorm(n_feats)

        def forward(self, x):
            residual = x
            x = self.cnn1(self.dropout1(F.gelu(self.layer_norm1(x))))
            x = self.cnn2(self.dropout2(F.gelu(self.layer_norm2(x))))
            return x + residual

    class BidirectionalLSTM(nn.Module):
        def __init__(self, rnn_dim, hidden_size, dropout, batch_first):
            super().__init__()
            self.BiLSTM = nn.LSTM(input_size=rnn_dim, hidden_size=hidden_size, num_layers=1,
                                  batch_first=batch_first, bidirectional=True)
            self.dropout = nn.Dropout(dropout)

        def forward(self, x):
            x, _ = self.BiLSTM(x)
            return self.dropout(x)

    class AcousticModel(nn.Module):
        def __init__(self, n_feats=32, rnn_dim=256, n_class=72, dropout=0.1):
            super().__init__()
            self.cnn_layers = nn.Sequential(nn.Conv2d(1, n_feats, 3, stride=1, padding=1),
                                            nn.ReLU())
            self.rescnn_layers = nn.Sequential(
                ResidualCNN(n_feats, n_feats, kernel=3, stride=1, dropout=dropout, n_feats=128))
            self.maxpooling = nn.MaxPool2d(kernel_size=(2, 3))
            self.fully_connected = nn.Linear(n_feats * 64, rnn_dim)
            self.bilstm = nn.Sequential(
                BidirectionalLSTM(rnn_dim, rnn_dim, dropout, batch_first=True),
                BidirectionalLSTM(rnn_dim * 2, rnn_dim, dropout, batch_first=False),
                BidirectionalLSTM(rnn_dim * 2, rnn_dim, dropout, batch_first=False))
            self.classifier = nn.Sequential(nn.Linear(rnn_dim * 2, n_class))

        def forward(self, x):
            x = self.maxpooling(self.rescnn_layers(self.cnn_layers(x)))
            sizes = x.size()
            x = x.view(sizes[0], sizes[1] * sizes[2], sizes[3]).transpose(1, 2)
            return self.classifier(self.bilstm(self.fully_connected(x)))

    return AcousticModel()


class Phonemizer:
    """IPA phonemes through espeak-ng (the build that ships with `espeakng-loader`)."""

    VOICES: ClassVar = {"en": "en-us", "de": "de", "fr": "fr-fr", "it": "it", "es": "es"}

    def __init__(self):
        self._backends: dict[str, object] = {}

    def supports(self, language: str) -> bool:
        return language.split("-")[0] in self.VOICES

    def phones(self, words: list[str], language: str) -> list[list[str]]:
        from phonemizer.separator import Separator

        backend = self._backend(language)
        out = backend.phonemize(words, separator=Separator(phone=";", word=None), strip=True)
        return [[p for p in w.split(";") if p] for w in out]

    def _backend(self, language: str):
        voice = self.VOICES[language.split("-")[0]]
        if voice not in self._backends:
            import espeakng_loader
            from phonemizer.backend import EspeakBackend
            from phonemizer.backend.espeak.wrapper import EspeakWrapper

            EspeakWrapper.set_library(espeakng_loader.get_library_path())
            EspeakWrapper.set_data_path(espeakng_loader.get_data_path())
            self._backends[voice] = EspeakBackend(voice, language_switch="remove-flags")
        return self._backends[voice]


class SingingPhonemeModel(IAcousticModel):
    name = "singing-phonemes"
    sample_rate = 22050
    FRAME_SECONDS = 256 / 22050 * 3
    word_gap = SPACE

    def __init__(self, checkpoint: Path, phonemizer: Phonemizer, device: str | None = None):
        import torch
        import torchaudio

        self._torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._phonemizer = phonemizer
        # Cached emissions are named after the model: a fine-tuned checkpoint gets its own.
        stat = checkpoint.stat()
        self.name = f"singing-phonemes-{stat.st_size:x}{int(stat.st_mtime):x}"[:40]
        self._network = build_network()
        state = torch.load(checkpoint, map_location="cpu", weights_only=False)
        self._network.load_state_dict(state["model_state_dict"])
        self._network.to(self.device).eval()
        self._mel = torchaudio.transforms.MelSpectrogram(
            sample_rate=self.sample_rate, n_mels=128, n_fft=512).to(self.device)

    def supports(self, language: str) -> bool:
        return self._phonemizer.supports(language)

    def emissions(self, samples: np.ndarray) -> Emissions:
        torch = self._torch
        with torch.inference_mode():
            x = torch.from_numpy(samples).float().to(self.device)[None]
            mel = self._mel(x)[None]  # (1, 1, 128, time)
            out = torch.log_softmax(self._network(mel), dim=2)[0]
        frames = int(len(samples) / self.sample_rate // self.FRAME_SECONDS)
        logp = out[:frames].float().cpu().numpy()
        return Emissions(logp=logp, frame_seconds=self.FRAME_SECONDS, blank=BLANK)

    def tokens(self, words: list[str], language: str) -> list[list[int]]:
        cleaned = [self._clean(w) for w in words]
        phones = self._phonemizer.phones([c or "a" for c in cleaned], language)
        return [[PHONE_ID.get(p, UNKNOWN) for p in ph] if c else []
                for c, ph in zip(cleaned, phones, strict=True)]

    @staticmethod
    def _clean(word: str) -> str:
        return "".join(ch for ch in word.lower() if ch.isalnum() or ch == "'").strip("'")

    def close(self) -> None:
        del self._network
        if self.device == "cuda":
            self._torch.cuda.empty_cache()
