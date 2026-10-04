from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration read from the environment or a `.env` file in the working directory."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="AUTOLYRICS_", extra="ignore")

    jobs_dir: Path = Path("jobs")

    # DeepSeek's API is OpenAI-compatible, so the base URL and model stay configurable.
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # Spotify Web API (client credentials) for resolving Spotify links.
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None


settings = Settings()
