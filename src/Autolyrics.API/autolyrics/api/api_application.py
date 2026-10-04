from contextlib import asynccontextmanager
from pathlib import Path
from typing import ClassVar

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from autolyrics.api.controllers import (
    health_controller,
    job_media_controller,
    jobs_controller,
)
from autolyrics.composition.container import Container
from autolyrics.domain.errors import (
    DomainError,
    InvalidInputError,
    JobNotFoundError,
    JobStateError,
    NotFoundError,
)
from autolyrics.infrastructure.paths import RepositoryPaths
from autolyrics.version import __version__


class DomainErrorResponses:
    """Maps domain errors to HTTP status codes."""

    STATUS: ClassVar = {JobNotFoundError: 404, NotFoundError: 404, JobStateError: 409,
              InvalidInputError: 400}

    def register(self, app: FastAPI) -> None:
        app.add_exception_handler(DomainError, self.handle)

    async def handle(self, _request: Request, error: DomainError) -> JSONResponse:
        status = next((code for kind, code in self.STATUS.items() if isinstance(error, kind)), 500)
        return JSONResponse({"detail": str(error)}, status_code=status)


class FrontendFiles:
    """Serves the built frontend, with every unknown path falling back to the single page."""

    def __init__(self, dist: Path):
        self._dist = dist

    def mount(self, app: FastAPI) -> None:
        if not (self._dist / "index.html").exists():
            return
        if (self._dist / "assets").exists():
            app.mount("/assets", StaticFiles(directory=self._dist / "assets"), name="assets")
        app.add_api_route("/{path:path}", self.serve, include_in_schema=False)

    # Hashed bundles under /assets may be cached forever; everything else (index.html, the logo)
    # must be revalidated, or a rebuilt frontend keeps showing stale files.
    REVALIDATE: ClassVar = {"Cache-Control": "no-cache"}

    async def serve(self, path: str) -> FileResponse:
        candidate = (self._dist / path).resolve()
        if path and candidate.is_file() and self._dist.resolve() in candidate.parents:
            return FileResponse(candidate, headers=self.REVALIDATE)
        return FileResponse(self._dist / "index.html", headers=self.REVALIDATE)


class ApiApplication:
    """The local HTTP API plus the static frontend: what `autolyrics serve` runs."""

    FRONTEND_DIST = RepositoryPaths.frontend_dist()

    def __init__(self, container: Container, frontend_dist: Path | None = None):
        self._container = container
        self._frontend = FrontendFiles(frontend_dist or self.FRONTEND_DIST)

    def build(self) -> FastAPI:
        app = FastAPI(title="autolyrics", version=__version__, lifespan=self._lifespan)
        app.state.container = self._container
        for module in (health_controller, jobs_controller, job_media_controller):
            app.include_router(module.router)
        DomainErrorResponses().register(app)
        self._frontend.mount(app)
        return app

    @asynccontextmanager
    async def _lifespan(self, _app: FastAPI):
        self._container.settings.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._container.queue.start(self._container.mediator)
        try:
            yield
        finally:
            await self._container.aclose()
