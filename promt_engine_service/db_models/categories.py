"""Category database models and schemas."""

from typing import List
import uuid

from pydantic import model_validator
from sqlalchemy import UniqueConstraint
from slugify import slugify
from sqlmodel import Column, Field, SQLModel

from auth_sdk_m8.models.shared import TimestampMixin
from promt_engine_service.core.config import settings
from promt_engine_service.core.db_models import UUIDString, prefixed_tables
from promt_engine_service.schemas.base import CategoryType


class CategoryBase(SQLModel):
    """Shared category fields."""

    name: str = Field(unique=True, min_length=1, max_length=50)
    slug: str = Field(unique=True, min_length=1, max_length=50, index=True)
    type: CategoryType = Field(sa_column_kwargs={"nullable": False})


class CategoryGenerators(CategoryBase):
    """Category schema with slug auto-generation."""

    @model_validator(mode="before")
    @classmethod
    def generate_slug(cls, values):
        """Auto-generate slug from name."""
        if isinstance(values, dict) and values.get("name"):
            values["slug"] = slugify(values["name"])
        return values


class CategoryCreate(CategoryGenerators):
    """Schema for creating a category."""


class CategoryUpdate(CategoryGenerators):
    """Schema for updating a category."""


class Category(TimestampMixin, CategoryBase, SQLModel, table=True):
    """Category table."""

    __tablename__ = prefixed_tables("category")
    __table_args__ = (
        UniqueConstraint("slug", name="uq_category_slug"),
        {"mysql_engine": settings.DB_ENGINE, "mysql_charset": settings.DB_CHARSET},
    )

    id: int = Field(default=None, primary_key=True, index=True)
    owner_id: uuid.UUID = Field(
        sa_column=Column("owner_id", UUIDString(), nullable=False, index=True),
        description="ID of the user who owns this category",
    )


class CategoryPublic(CategoryBase, SQLModel):
    """Public category representation."""

    id: int
    owner_id: uuid.UUID


class CategoriesPublic(SQLModel):
    """Paginated category list."""

    data: List[CategoryPublic]
    count: int