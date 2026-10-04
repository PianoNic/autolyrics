import logging
import shutil
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)


class ModelFiles:
    """Model weights that are not on PyPI, downloaded once into the models folder."""

    SINGING_URL = ("https://github.com/jhuang448/LyricsAlignment-Multilingual/raw/main/"
                   "checkpoints/checkpoint_Baseline")

    def __init__(self, root: Path):
        self._root = root

    def singing_checkpoint(self) -> Path:
        path = self._root / "singing" / "checkpoint_Baseline"
        legacy = self._root / "third_party" / "lam" / "checkpoints" / "checkpoint_Baseline"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            if legacy.exists():
                shutil.copyfile(legacy, path)
            else:
                log.info("downloading the singing acoustic model (57 MB)")
                partial = path.with_suffix(".part")
                urllib.request.urlretrieve(self.SINGING_URL, partial)
                partial.replace(path)
        return path
