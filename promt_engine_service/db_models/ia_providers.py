"""LLM provider database models."""

from typing import List
import uuid

from pydantic import SecretStr, model_validator
from sqlalchemy import Column, UniqueConstraint
from slugify import slugify
from sqlmodel import Column, Field, SQLModel

from auth_sdk_m8.models.shared import TimestampMixin
from promt_engine_service.core.config import settings
from promt_engine_service.core.db_models import UUIDString, prefixed_tables
from promt_engine_service.schemas.base import LLMProviderType


class LLMProviderBase(SQLModel):
    """Shared LLM provider fields."""

    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(unique=True, min_length=1, max_length=100, index=True)
    type: LLMProviderType = Field(sa_column_kwargs={"nullable": False})


class LLMProviderCreate(LLMProviderBase):
    """Create payload for an LLM provider."""

    api_key: SecretStr = Field(min_length=1, max_length=500, repr=False)

    @model_validator(mode="before")
    @classmethod
    def generate_slug(cls, values):
        """Generate a normalized slug from name."""
        if isinstance(values, dict) and isinstance(values.get("name"), str):
            values["slug"] = slugify(values["name"])
        return values


class LLMProvider(TimestampMixin, LLMProviderBase, SQLModel, table=True):
    """LLM provider table.

    The API key is intentionally excluded from public schemas and repr output.
    Secret storage/encryption should be handled by the deployment secret layer.
    """

    __tablename__ = prefixed_tables("llm_provider")
    __table_args__ = (
        UniqueConstraint("slug", name="uq_llm_providers_slug"),
        {"mysql_engine": settings.DB_ENGINE, "mysql_charset": settings.DB_CHARSET},
    )

    id: int = Field(default=None, primary_key=True, index=True)
    owner_id: uuid.UUID = Field(
        sa_column=Column("owner_id", UUIDString(), nullable=False, index=True),
        description="UUID of the owning user",
    )
    api_key: str = Field(min_length=1, max_length=500, repr=False)


class LLMProviderPublic(LLMProviderBase, SQLModel):
    """Public LLM provider representation without secret material."""

    id: int
    owner_id: uuid.UUID


class LLMProvidersPublic(SQLModel):
    """Paginated LLM provider list."""

    data: List[LLMProviderPublic]
    count: int