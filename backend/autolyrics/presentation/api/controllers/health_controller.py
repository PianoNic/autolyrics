from fastapi import APIRouter, Depends

from autolyrics import __version__
from autolyrics.composition.container import Container
from autolyrics.presentation.api.controller import controller
from autolyrics.presentation.api.dependencies import ApiDependencies
from autolyrics.presentation.api.schemas import HealthResponse

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
