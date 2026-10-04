from pydantic import BaseModel


class CreateJobRequest(BaseModel):
    url: str
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    skip_llm: bool = False


class RealignLineRequest(BaseModel):
    text: str | None = None
    start: float | None = None
    end: float | None = None


class HealthResponse(BaseModel):
    ok: bool
    version: str
    llm: bool
    lyrics_api_key: bool
