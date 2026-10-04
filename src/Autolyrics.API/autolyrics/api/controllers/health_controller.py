from fastapi import APIRouter, Depends

from autolyrics.api.controller import controller
from autolyrics.api.dependencies import ApiDependencies
from autolyrics.api.schemas import HealthResponse
from autolyrics.composition.container import Container
from autolyrics.version import __version__

router = APIRouter(prefix="/api", tags=["Health"])


@controller(router)
class HealthController:
    container: Container = Depends(ApiDependencies.container)

    @router.get("/health")
    async def health(self) -> HealthResponse:
        settings = self.container.settings
        return HealthResponse(ok=True, version=__version__, llm=bool(settings.llm_api_key),
                              lyrics_api_key=bool(settings.boidu_api_key),
                              apple_music=bool(settings.apple_music_user_token))
