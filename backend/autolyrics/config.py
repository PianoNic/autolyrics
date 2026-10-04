from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration read from the environment or a `.env` file in the working directory."""

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    jobs_dir: Path = Field(Path("jobs"), validation_alias="AUTOLYRICS_JOBS_DIR")

    # ArgonFetch resolves song links (Spotify, YouTube, SoundCloud, ...) and serves the audio.
    argonfetch_base_url: str = Field(
        "https://app.argonfetch.dev", validation_alias="AUTOLYRICS_ARGONFETCH_BASE_URL"
    )

    # OpenAI-compatible endpoint serving DeepSeek, used for the final text clean-up only.
    llm_base_url: str = Field(
        "https://api.deepseek.com",
        validation_alias=AliasChoices("AGENT_BASE_URL", "AUTOLYRICS_LLM_BASE_URL"),
    )
    llm_api_key: str | None = Field(
        None, validation_alias=AliasChoices("AGENT_API_KEY", "AUTOLYRICS_LLM_API_KEY")
    )
    llm_model: str = Field(
        "sgl/deepseek", validation_alias=AliasChoices("AGENT_MODEL", "AUTOLYRICS_LLM_MODEL")
    )

    # How far a lyrics source's length may differ from the audio before it counts as another
    # version of the song (e.g. a live session versus the studio recording).
    duration_tolerance: float = Field(3.0, validation_alias="AUTOLYRICS_DURATION_TOLERANCE")


settings = Settings()
