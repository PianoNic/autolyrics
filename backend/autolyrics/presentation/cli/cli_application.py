"""Command line: `autolyrics run <link>` for one song, `autolyrics serve` for the web app."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import ClassVar

from mediatorx import INotificationHandler

from autolyrics.application.jobs.create_job import CreateJobCommand
from autolyrics.application.jobs.notifications import JobEventRaised
from autolyrics.application.jobs.run_job import RunJobCommand
from autolyrics.composition.container import Container
from autolyrics.domain.job import JobOptions, JobStatus


class ConsoleProgressPrinter(INotificationHandler[JobEventRaised]):
    ICONS: ClassVar = {"running": "…", "done": "✓", "skipped": "–", "failed": "✗"}

    async def handle(self, notification: JobEventRaised) -> None:
        event = notification.event
        print(f"  {self.ICONS.get(event.status.value, '?')} {event.stage.value:<8} "
              f"{event.message}", flush=True)


class CliApplication:
    COMMANDS = ("run", "serve")

    def __init__(self, container_factory=Container):
        self._container_factory = container_factory

    @classmethod
    def main(cls, argv: list[str] | None = None) -> int:
        return cls().execute(sys.argv[1:] if argv is None else argv)

    def execute(self, argv: list[str]) -> int:
        # `autolyrics <link>` is shorthand for `autolyrics run <link>`.
        if argv and argv[0] not in self.COMMANDS and not argv[0].startswith("-"):
            argv = ["run", *argv]
        args = self._parser().parse_args(argv)
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                            format="    %(levelname)s %(name)s: %(message)s")
        if args.command == "serve":
            return self._serve(args)
        return asyncio.run(self._run(args))

    def _parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="autolyrics", description=__doc__)
        parser.add_argument("-v", "--verbose", action="store_true")
        commands = parser.add_subparsers(dest="command", required=True)

        run = commands.add_parser("run", help="process one song and write its lyrics files")
        run.add_argument("url", help="Spotify, YouTube, SoundCloud, ... link to the song")
        run.add_argument("--title", help="override the detected song title")
        run.add_argument("--artist", help="override the detected artist")
        run.add_argument("--album", help="album name, helps some lyrics sources")
        run.add_argument("--lyrics", type=Path, help="use this TTML/LRC/QRC/TXT instead of searching")
        run.add_argument("--job-id", help="reuse or name the job directory under the jobs folder")
        run.add_argument("--no-llm", action="store_true", help="skip the DeepSeek clean-up")
        run.add_argument("-v", "--verbose", action="store_true")

        serve = commands.add_parser("serve", help="run the local web app")
        serve.add_argument("--host", default="127.0.0.1")
        serve.add_argument("--port", type=int, default=8765)
        serve.add_argument("-v", "--verbose", action="store_true")
        return parser

    async def _run(self, args: argparse.Namespace) -> int:
        container = self._container_factory()
        container.on(JobEventRaised, ConsoleProgressPrinter, ConsoleProgressPrinter)
        try:
            options = JobOptions(url=args.url, title=args.title, artist=args.artist,
                                 album=args.album,
                                 lyrics_file=str(args.lyrics) if args.lyrics else None,
                                 skip_llm=args.no_llm)
            created = await container.mediator.send(
                CreateJobCommand(options, enqueue=False, job_id=args.job_id))
            result = await container.mediator.send(RunJobCommand(created.id))
        finally:
            await container.aclose()
        output = container.repository.output_directory(result.id)
        if result.status != JobStatus.DONE:
            print(f"\nFailed: {result.error}", file=sys.stderr)
            return 1
        print(f"\nDone: {output}")
        return 0

    def _serve(self, args: argparse.Namespace) -> int:
        import uvicorn

        from autolyrics.presentation.api.api_application import ApiApplication

        app = ApiApplication(self._container_factory()).build()
        print(f"autolyrics on http://{args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port,
                    log_level="info" if args.verbose else "warning")
        return 0
