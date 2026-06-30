"""Base prompt-engine schemas."""

from enum import Enum


class CategoryType(str, Enum):
    """Category ownership target."""

    PROMPT_BLOCK = "prompt_block"
    PROMPT_TEMPLATE = "prompt_template"


class PromptBlockType(str, Enum):
    """Supported prompt block roles."""

    ROLE = "role"
    TASK = "task"
    CONTEXT = "context"
    INSTRUCTION = "instruction"
    EXAMPLE = "example"
    FORMAT = "format"


class LLMProviderType(str, Enum):
    """Supported LLM provider types."""

    MISTRAL = "mistral"
    OPENAI = "openai"
