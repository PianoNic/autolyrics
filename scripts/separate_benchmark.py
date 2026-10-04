"""Separate every benchmark song once with the RoFormer chain; stems land in <song>/v2/.

    python scripts/separate_benchmark.py [benchmarks_dir]
"""

import json
import sys
import time
from pathlib import Path

from autolyrics.infrastructure.clients.media.ffmpeg import Ffmpeg
from autolyrics.infrastructure.services.ml.roformer_separator import RoformerVocalSeparator
from autolyrics.infrastructure.services.runtime.background_priority import BackgroundPriority


def main() -> None:
    BackgroundPriority().apply()
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("benchmarks")
    separator = RoformerVocalSeparator(Ffmpeg(), root.parent / "models" / "separator")
    for folder in sorted(p for p in root.iterdir() if (p / "meta.json").exists()):
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        workspace = folder / "v2"
        workspace.mkdir(exist_ok=True)
        started = time.time()
        try:
            separator.stems(folder / meta["audio"], workspace)
            print(f"{folder.name:45s} {time.time() - started:.0f}s", flush=True)
        except Exception as error:  # noqa: BLE001 - report and continue
            print(f"{folder.name:45s} failed: {error}", flush=True)


if __name__ == "__main__":
    main()
