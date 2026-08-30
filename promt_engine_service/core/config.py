"""Configuration settings for promt_engine_service.

Prompt-engine specific fields only; auth, observability, database, and
consumer wiring are inherited from ``ConsumerServiceSettings``.
"""

from pathlib import Path
from typing import ClassVar

from fastapi_m8 import ConsumerServiceSettings, find_dotenv
from pydantic_settings import SettingsConfigDict

from promt_engine_service import __version__


class Settings(ConsumerServiceSettings):
    """promt_engine_service settings extending ConsumerServiceSettings."""

    ENV_FILE_DIR: ClassVar[Path] = Path(__file__).resolve().parent

    model_config = SettingsConfigDict(
        env_file=find_dotenv(Path(__file__).resolve().parent),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="forbid",
    )

    SERVICE_VERSION: str = __version__
    CONTRACT_NAME: str = "prompt-engine-m8"
    CONTRACT_VERSION: str = "2.1.0"
    #: Raised with the contract axis: the supported floor is 2.1.0, not 2.0.0.
    #: ``A-C8``'s export routes are additive, so a 2.0 caller is still *served*,
    #: but the range states what this release supports rather than what it
    #: happens to tolerate — a 2.0 client is expected to move with the pair.
    CONTRACT_RANGE: str = ">=2.1.0 <3.0.0"


try:
    settings = Settings()
except Exception as exc:  # pragma: no cover
    raise RuntimeError(f"Configuration validation error:\n {exc}") from exc
