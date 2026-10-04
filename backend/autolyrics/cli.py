"""Command line: `autolyrics <song link>`."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from autolyrics.pipeline import Event, Job, JobOptions, PipelineError

_ICONS = {"running": "…", "done": "✓", "skipped": "–", "failed": "✗"}


def _print_event(event: Event) -> None:
    print(f"  {_ICONS.get(event.status, '?')} {event.stage:<8} {event.message}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="autolyrics", description=__doc__)
    parser.add_argument("url", help="Spotify, YouTube, SoundCloud, ... link to the song")
    parser.add_argument("--title", help="override the detected song title")
    parser.add_argument("--artist", help="override the detected artist")
    parser.add_argument("--album", help="album name, helps some lyrics sources")
    parser.add_argument("--lyrics", type=Path, help="use this TTML/LRC/QRC/TXT instead of searching")
    parser.add_argument("--job-dir", type=Path, help="where to put downloads and output")
    parser.add_argument("--no-llm", action="store_true", help="skip the DeepSeek clean-up")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="    %(levelname)s %(name)s: %(message)s")

    job = Job(JobOptions(url=args.url, title=args.title, artist=args.artist, album=args.album,
                         lyrics_file=args.lyrics, skip_llm=args.no_llm), on_event=_print_event, job_dir=args.job_dir)
    try:
        asyncio.run(job.run())
    except PipelineError as error:
        job.save_report()
        print(f"\nFailed at {error.stage}: {error}", file=sys.stderr)
        return 1
    print(f"\nDone: {job.job_dir / 'output'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
