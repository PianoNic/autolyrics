import gc
import logging
import shutil
from pathlib import Path

from autolyrics.application.interfaces.audio import IVocalSeparator, VocalStems
from autolyrics.application.interfaces.progress import NO_PROGRESS, IProgress
from autolyrics.infrastructure.media.ffmpeg import Ffmpeg

log = logging.getLogger(__name__)


class RoformerVocalSeparator(IVocalSeparator):
    """Three RoFormer passes through python-audio-separator, each about 2.5 dB cleaner than
    Demucs on vocals:

    1. vocals from the mix
    2. lead from backing ("karaoke" model): background lines are timed on the backing stem, so
       the two voices stop stealing each other's words
    3. reverb and echo off the lead: a tail of reverb is what made held words run long
    """

    VOCALS = "vocals.wav"  # all vocals: transcription hears everything
    LEAD = "lead.wav"  # dry lead vocal: what the main lines are timed against
    BACKING = "backing.wav"

    def __init__(self, ffmpeg: Ffmpeg, model_dir: Path,
                 vocals_model: str = "mel_band_roformer_kim_ft2_bleedless_unwa.ckpt",
                 karaoke_model: str = "mel_band_roformer_karaoke_becruily.ckpt",
                 dereverb_model: str = "dereverb_mel_band_roformer_less_aggressive_anvuew_sdr_18.8050.ckpt"):
        self._ffmpeg = ffmpeg
        self._model_dir = model_dir
        self._steps = (vocals_model, karaoke_model, dereverb_model)

    def stems(self, audio: Path, workspace: Path,
              progress: IProgress = NO_PROGRESS) -> VocalStems:
        vocals, lead, backing = (workspace / self.VOCALS, workspace / self.LEAD,
                                 workspace / self.BACKING)
        if not (vocals.exists() and lead.exists() and backing.exists()):
            self._separate(audio, workspace, progress)
        return VocalStems(lead=lead, vocals=vocals, backing=backing)

    def _separate(self, audio: Path, workspace: Path, progress: IProgress) -> None:
        scratch = workspace / "separation"
        scratch.mkdir(exist_ok=True)
        try:
            mix = self._ffmpeg.to_wav(audio, scratch / "mix.wav", sample_rate=44100)
            vocals_model, karaoke_model, dereverb_model = self._steps
            progress.update(0.0, "vocals from the mix")
            vocals = self._run(vocals_model, mix, scratch, keep="vocals")
            progress.update(1 / 3, "lead from backing vocals")
            lead, backing = self._run(karaoke_model, vocals, scratch, keep="vocals",
                                      other="instrumental")
            progress.update(2 / 3, "reverb off the lead")
            dry = self._run(dereverb_model, lead, scratch, keep="noreverb")
            shutil.move(vocals, workspace / self.VOCALS)
            shutil.move(backing, workspace / self.BACKING)
            shutil.move(dry, workspace / self.LEAD)
            progress.update(1.0, "done")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
            self._free_gpu()

    def _run(self, model: str, source: Path, out: Path, keep: str, other: str | None = None):
        from audio_separator.separator import Separator

        separator = Separator(output_dir=str(out), model_file_dir=str(self._model_dir),
                              output_format="WAV", log_level=logging.WARNING)
        separator.load_model(model)
        files = [out / Path(f).name for f in separator.separate(str(source))]
        del separator
        self._free_gpu()
        # Each pass appends its model name to the file name; short names keep the next pass
        # under Windows' 260-character path limit.
        wanted = self._short(self._stem(files, keep), out, keep)
        if other is None:
            return wanted
        return wanted, self._short(self._stem(files, other), out, other)

    @staticmethod
    def _short(path: Path, out: Path, name: str) -> Path:
        target = out / f"{len(list(out.glob('*.wav')))}-{name}.wav"
        path.replace(target)
        return target

    @staticmethod
    def _stem(files: list[Path], name: str) -> Path:
        """audio-separator names outputs `<input>_(<Stem>)_<model>.wav`; an input name that
        already carries a stem name is why only the last bracket counts."""
        for f in files:
            stems = [part.split(")")[0].lower() for part in f.stem.split("_(")[1:]]
            if stems and stems[-1] == name:
                return f
        raise RuntimeError(f"separation produced no {name} stem: {[f.name for f in files]}")

    @staticmethod
    def _free_gpu() -> None:
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
