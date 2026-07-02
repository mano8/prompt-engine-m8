"""Prompt database models."""

from typing import Optional
import uuid

from sqlalchemy import TEXT, Column, UniqueConstraint
from slugify import slugify
from sqlmodel import Field, Relationship, SQLModel

from auth_sdk_m8.models.shared import TimestampMixin
from auth_sdk_m8.schemas.shared import ValidationConstants
from promt_engine_service.core.config import settings
from promt_engine_service.core.db_models import UUIDString, prefixed_fk, prefixed_tables
from promt_engine_service.schemas.base import PromptBlockType


class PromptBlockBase(SQLModel):
    """Shared prompt block fields."""

    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(unique=True, min_length=1, max_length=100, index=True)
    description: Optional[str] = Field(
        default=None,
        sa_column=Column(TEXT(), nullable=True),
        max_length=1000,
    )
    content: str = Field(
        sa_column=Column(TEXT(), nullable=False),
        max_length=5000,
    )
    type: PromptBlockType = Field(sa_column_kwargs={"nullable": False})
    is_dynamic: bool = Field(default=False)
    is_public: bool = Field(default=False)


class PromptBlockGenerators(PromptBlockBase):
    """Validation helpers for prompt blocks."""

    @classmethod
    def generate_slug_and_sanitize(cls, values):
        """Generate slug and strip invisible chars."""
        if isinstance(values, dict):
            name = values.get("name")
            if isinstance(name, str):
                values["slug"] = slugify(name)
            for key in ("content", "description"):
                text = values.get(key)
                if isinstance(text, str):
                    values[key] = ValidationConstants.remove_invisible_chars(text)
        return values


class PromptBlock(TimestampMixin, PromptBlockBase, SQLModel, table=True):
    """Reusable prompt block table."""

    __tablename__ = prefixed_tables("prompt_blocks")
    __table_args__ = (
        UniqueConstraint("slug", name="uq_prompt_blocks_slug"),
        {"mysql_engine": settings.DB_ENGINE, "mysql_charset": settings.DB_CHARSET},
    )

    id: int = Field(default=None, primary_key=True, index=True)
    owner_id: uuid.UUID = Field(
        sa_column=Column("owner_id", UUIDString(), nullable=False, index=True),
        description="UUID of the owning user",
    )
    templates: list["TemplateBlock"] = Relationship(back_populates="block")


class PromptBlockPublic(PromptBlockBase, SQLModel):
    """Public prompt block representation."""

    id: int
    owner_id: uuid.UUID


class PromptBlocksPublic(SQLModel):
    """Paginated prompt block list."""

    data: list[PromptBlockPublic]
    count: int


class PromptTemplateBase(TimestampMixin, SQLModel):
    """Shared prompt template fields."""

    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(unique=True, min_length=1, max_length=100, index=True)
    description: Optional[str] = Field(
        default=None,
        sa_column=Column(TEXT(), nullable=True),
        max_length=1000,
    )
    is_public: bool = Field(default=True)


class PromptTemplate(PromptTemplateBase, SQLModel, table=True):
    """Prompt template table."""

    __tablename__ = prefixed_tables("prompt_templates")
    __table_args__ = (
        UniqueConstraint("slug", name="uq_prompt_templates_slug"),
        {"mysql_engine": settings.DB_ENGINE, "mysql_charset": settings.DB_CHARSET},
    )

    id: int = Field(default=None, primary_key=True, index=True)
    owner_id: uuid.UUID = Field(
        sa_column=Column("owner_id", UUIDString(), nullable=False, index=True),
        description="Owning user ID",
    )
    blocks: list["TemplateBlock"] = Relationship(
        back_populates="template",
        sa_relationship_kwargs={"order_by": "TemplateBlock.position"},
    )


class PromptTemplatePublic(PromptTemplateBase, SQLModel):
    """Public prompt template representation."""

    id: int
    owner_id: uuid.UUID


class PromptTemplatesPublic(SQLModel):
    """Paginated prompt template list."""

    data: list[PromptTemplatePublic]
    count: int


class TemplateBlockBase(SQLModel):
    """Shared template-block fields."""

    position: int = Field(nullable=False, ge=1)


class TemplateBlockCreate(TemplateBlockBase):
    """Create a template-block link."""

    template_id: int = Field(foreign_key=prefixed_fk("prompt_templates", "id"))
    block_id: int = Field(foreign_key=prefixed_fk("prompt_blocks", "id"))


class TemplateBlockUpdate(TemplateBlockCreate):
    """Update a template-block link."""


class TemplateBlock(TemplateBlockBase, SQLModel, table=True):
    """Join table between templates and blocks."""

    __tablename__ = prefixed_tables("template_blocks")
    __table_args__ = (
        UniqueConstraint("template_id", "position", name="uq_template_position"),
        UniqueConstraint("template_id", "block_id", name="uq_template_block"),
        {"mysql_engine": settings.DB_ENGINE, "mysql_charset": settings.DB_CHARSET},
    )

    id: int = Field(default=None, primary_key=True, index=True)
    template_id: int = Field(
        foreign_key=prefixed_fk("prompt_templates", "id"), nullable=False, index=True
    )
    block_id: int = Field(
        foreign_key=prefixed_fk("prompt_blocks", "id"), nullable=False, index=True
    )
    position: int

    template: PromptTemplate = Relationship(back_populates="blocks")
    block: PromptBlock = Relationship(back_populates="templates")


class TemplateBlockPublic(SQLModel):
    """Public template-block representation."""

    id: int
    template_id: int
    block: PromptBlockPublic
    position: int


class TemplateBlocksPublic(SQLModel):
    """Paginated template-block list."""

    data: list[TemplateBlockPublic]
    count: int
