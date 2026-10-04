from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration read from the environment or a `.env` file in the working directory."""

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore",
                                      populate_by_name=True)

    jobs_dir: Path = Field(Path("jobs"), validation_alias="AUTOLYRICS_JOBS_DIR")

    # ArgonFetch resolves song links (Spotify, YouTube, SoundCloud, ...) and serves the audio.
    argonfetch_base_url: str = Field(
        "https://app.argonfetch.dev", validation_alias="AUTOLYRICS_ARGONFETCH_BASE_URL")

    # OpenAI-compatible endpoint serving DeepSeek, used for the final text clean-up only.
    llm_base_url: str = Field(
        "https://api.deepseek.com",
        validation_alias=AliasChoices("AGENT_BASE_URL", "AUTOLYRICS_LLM_BASE_URL"))
    llm_api_key: str | None = Field(
        None, validation_alias=AliasChoices("AGENT_API_KEY", "AUTOLYRICS_LLM_API_KEY"))
    llm_model: str = Field(
        "sgl/deepseek", validation_alias=AliasChoices("AGENT_MODEL", "AUTOLYRICS_LLM_MODEL"))

    # lyrics-api.boidu.dev (Better Lyrics TTML, QQ QRC) answers cached songs without a key and
    # needs one for everything else.
    boidu_api_key: str | None = Field(None, validation_alias="AUTOLYRICS_BOIDU_API_KEY")

    # How far a lyrics source's length may differ from the audio before it counts as another
    # cut of the song (e.g. a music video versus the album version).
    duration_tolerance: float = Field(3.0, validation_alias="AUTOLYRICS_DURATION_TOLERANCE")

    # Demucs model for vocal isolation; htdemucs_ft is about 4x slower than htdemucs but cleaner.
    demucs_model: str = Field("htdemucs_ft", validation_alias="AUTOLYRICS_DEMUCS_MODEL")

    # Whisper model for songs no lyrics source has (transformers model id).
    whisper_model: str = Field("openai/whisper-large-v3-turbo",
                               validation_alias="AUTOLYRICS_WHISPER_MODEL")
