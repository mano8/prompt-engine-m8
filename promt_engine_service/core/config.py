"""Configuration settings for promt_engine_service.

Prompt-engine specific fields only; auth, observability, database, and
consumer wiring are inherited from ``ConsumerServiceSettings``.
"""

from pathlib import Path

from auth_sdk_m8.utils.paths import find_dotenv
from fastapi_m8 import ConsumerServiceSettings
from pydantic_settings import SettingsConfigDict

from promt_engine_service import __version__


class Settings(ConsumerServiceSettings):
    """promt_engine_service settings extending ConsumerServiceSettings."""

    ENV_FILE_DIR: Path = Path(__file__).resolve().parent

    model_config = SettingsConfigDict(
        env_file=find_dotenv(Path(__file__).resolve().parent),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="forbid",
    )

    SERVICE_VERSION: str = __version__
    CONTRACT_NAME: str = "prompt-engine-m8"
    CONTRACT_VERSION: str = "1.0"
    CONTRACT_RANGE: str = ">=1.1.0 <2.0.0"


try:
    settings = Settings()
except Exception as exc:  # pragma: no cover
    raise RuntimeError(f"Configuration validation error:\n {exc}") from exc
