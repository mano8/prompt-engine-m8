"""Prompt and template API schemas."""

from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    model_validator,
)
from slugify import slugify
from typing_extensions import Annotated, TypedDict

from auth_sdk_m8.schemas.shared import ValidationConstants
from promt_engine_service.schemas.base import PromptBlockType


class TemplateBlockDict(TypedDict):
    """Serialized prompt block attached to a template."""

    id: int
    block_id: int
    template_id: int
    name: str
    slug: str
    description: Optional[str]
    content: str
    type: str
    is_dynamic: bool
    is_public: bool
    position: int


class PromptTemplateDict(TypedDict):
    """Serialized prompt template with ordered blocks."""

    id: int
    name: str
    slug: str
    description: Optional[str]
    is_public: bool
    blocks: list[TemplateBlockDict]


class PromptTemplatesList(BaseModel):
    """Prompt template list response."""

    count: int
    data: list[PromptTemplateDict]


class DynamicBlock(BaseModel):
    """Dynamic content supplied when composing a template."""

    id: int = Field(gt=0)
    content: Annotated[StrictStr, Field(min_length=1, max_length=5000)]

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def sanitize_content(cls, values):
        """Remove invisible characters from caller-supplied prompt content."""
        content = values.get("content") if isinstance(values, dict) else None
        if isinstance(content, str):
            values["content"] = ValidationConstants.remove_invisible_chars(content)
        return values


class PromptBlockModel(BaseModel):
    """Create/update payload for a reusable prompt block."""

    name: Annotated[StrictStr, Field(min_length=1, max_length=100)]
    description: Optional[Annotated[StrictStr, Field(max_length=1000)]] = None
    content: Annotated[StrictStr, Field(min_length=1, max_length=5000)]
    type: PromptBlockType
    is_dynamic: StrictBool = Field(default=False)
    is_public: StrictBool = Field(default=False)
    slug: Optional[StrictStr] = None

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    @model_validator(mode="before")
    @classmethod
    def generate_slug_and_sanitize(cls, values):
        """Generate a normalized slug and strip invisible prompt characters."""
        if not isinstance(values, dict):
            return values
        name = values.get("name")
        if isinstance(name, str):
            values["slug"] = slugify(name)
        for key in ("content", "description"):
            text = values.get(key)
            if isinstance(text, str):
                values[key] = ValidationConstants.remove_invisible_chars(text)
        return values


class PromptTemplateModel(BaseModel):
    """Create/update payload for a prompt template."""

    name: Annotated[StrictStr, Field(min_length=1, max_length=100)]
    description: Optional[Annotated[StrictStr, Field(max_length=1000)]] = None
    is_public: StrictBool = Field(default=False)
    slug: Optional[StrictStr] = None

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    @model_validator(mode="before")
    @classmethod
    def generate_slug_and_sanitize(cls, values):
        """Generate a normalized slug and strip invisible description chars."""
        if not isinstance(values, dict):
            return values
        name = values.get("name")
        if isinstance(name, str):
            values["slug"] = slugify(name)
        desc = values.get("description")
        if isinstance(desc, str):
            values["description"] = ValidationConstants.remove_invisible_chars(desc)
        return values
