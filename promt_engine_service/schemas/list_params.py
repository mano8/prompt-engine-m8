"""Declared list-query vocabulary for the prompt-engine list endpoints.

This module is the *published* half of the list contract. Every value a caller
may put in ``csrc``, ``sort``, ``order`` or ``f`` is named here as an enum
member, so the vocabulary reaches the OpenAPI document verbatim and a client
can mirror it instead of guessing at it.

Nothing here touches SQL. The mapping from a declared name to a real column or
predicate lives beside the queries in :mod:`promt_engine_service.controllers.prompts`,
and the contract tests assert the two halves stay in step — a name declared
here with no column behind it, or a column reachable without being declared
here, is a test failure rather than a runtime surprise.

Rejection is the point. A value that is not declared here is a ``422``, never a
silently ignored parameter: silent ignore is exactly what let a client render
server-driven search, sort and pagination controls against a service that
answered none of them.
"""

from enum import Enum
from typing import Annotated, Any, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict

#: Upper bound on ``q``. A free-text term is bound as a parameter, never
#: interpolated, but an unbounded one is still an unbounded scan.
MAX_SEARCH_LENGTH = 200

#: Upper bound on ``limit``. ``q`` compiles to a leading-wildcard ``LIKE`` over
#: every declared column — ``content`` included, which is unindexed text — so
#: the page a caller may ask for has to be bounded by something other than the
#: caller. This bounds what a single request *materialises*; it does not bound
#: the scan itself, which is a function of table size and indexing rather than
#: of ``limit``. The tables page at 10/20/40, so this leaves wide headroom.
MAX_PAGE_SIZE = 500

#: ``f`` carries several facet values in one query parameter.
FACET_SEPARATOR = ","


class ListSortOrder(str, Enum):
    """Sort direction accepted by every list endpoint."""

    ASC = "asc"
    DESC = "desc"


class PromptBlockSearchField(str, Enum):
    """Columns ``q`` may scan on ``GET /prompt-block/``."""

    NAME = "name"
    SLUG = "slug"
    DESCRIPTION = "description"
    CONTENT = "content"


class PromptBlockSortField(str, Enum):
    """Columns ``sort`` may order by on ``GET /prompt-block/``."""

    ID = "id"
    NAME = "name"
    SLUG = "slug"
    TYPE = "type"
    IS_DYNAMIC = "is_dynamic"
    IS_PUBLIC = "is_public"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class PromptBlockFacet(str, Enum):
    """Values ``f`` may carry on ``GET /prompt-block/``.

    The first six mirror :class:`~promt_engine_service.schemas.base.PromptBlockType`
    one-for-one; the last four are the two boolean axes the block library
    filters on. Selected facets combine with ``OR``, matching the faceted-filter
    control that produces them.
    """

    ROLE = "role"
    TASK = "task"
    CONTEXT = "context"
    INSTRUCTION = "instruction"
    EXAMPLE = "example"
    FORMAT = "format"
    DYNAMIC = "dynamic"
    STATIC = "static"
    PUBLIC = "public"
    PRIVATE = "private"


class PromptTemplateSearchField(str, Enum):
    """Columns ``q`` may scan on ``GET /prompt-template/``."""

    NAME = "name"
    SLUG = "slug"
    DESCRIPTION = "description"


class PromptTemplateSortField(str, Enum):
    """Columns ``sort`` may order by on ``GET /prompt-template/``.

    ``block_count`` is not a column — it is the number of blocks attached to
    the template, ordered by a correlated subquery. It is declared because the
    template table offers that column to the user, and a control the UI renders
    must be one the service answers.
    """

    ID = "id"
    NAME = "name"
    SLUG = "slug"
    IS_PUBLIC = "is_public"
    BLOCK_COUNT = "block_count"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class PromptTemplateFacet(str, Enum):
    """Values ``f`` may carry on ``GET /prompt-template/``."""

    PUBLIC = "public"
    PRIVATE = "private"


class CategorySortField(str, Enum):
    """Columns ``sort`` may order by on ``GET /category/``."""

    ID = "id"
    NAME = "name"
    SLUG = "slug"
    TYPE = "type"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class CategorySearchField(str, Enum):
    """Columns ``q`` scans on ``GET /category/``.

    Declared for the same reason as the others even though the category
    endpoint offers no ``csrc``: the columns a free-text term reaches are part
    of the contract whether or not the caller can narrow them.
    """

    NAME = "name"
    SLUG = "slug"


class ListVocabulary(BaseModel):
    """The allow-lists one list endpoint honours.

    Mirror this on the client rather than restating it: ``q_columns`` feeds no
    client control directly, but ``csrc``, ``sort`` and ``facets`` are exactly
    the ``allowedSearch`` / ``allowedSorts`` / ``allowedFilters`` a server-driven
    table needs. An empty tuple means the endpoint does not offer that
    parameter at all.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    resource: str
    q_columns: tuple[str, ...]
    csrc: tuple[str, ...]
    sort: tuple[str, ...]
    facets: tuple[str, ...]


def _values(enum_type: type[Enum]) -> tuple[str, ...]:
    """Declared member values, in declaration order."""
    return tuple(str(member.value) for member in enum_type)


PROMPT_BLOCK_LIST_VOCABULARY = ListVocabulary(
    resource="prompt-block",
    q_columns=_values(PromptBlockSearchField),
    csrc=_values(PromptBlockSearchField),
    sort=_values(PromptBlockSortField),
    facets=_values(PromptBlockFacet),
)

PROMPT_TEMPLATE_LIST_VOCABULARY = ListVocabulary(
    resource="prompt-template",
    q_columns=_values(PromptTemplateSearchField),
    csrc=_values(PromptTemplateSearchField),
    sort=_values(PromptTemplateSortField),
    facets=_values(PromptTemplateFacet),
)

CATEGORY_LIST_VOCABULARY = ListVocabulary(
    resource="category",
    q_columns=_values(CategorySearchField),
    csrc=(),
    sort=_values(CategorySortField),
    facets=(),
)


def blank_to_none(value: Any) -> Any:
    """Read an empty query parameter as an absent one.

    A table control that has nothing selected sends the parameter as an empty
    string rather than omitting it. Empty means "no column chosen", which is
    the default, not an undeclared value — rejecting it would make the honest
    default a ``422`` while teaching nobody anything.
    """
    if isinstance(value, str) and not value.strip():
        return None
    return value


#: Applied to every enum-typed list parameter, so "unset" and "absent" agree.
BlankAsAbsent = BeforeValidator(blank_to_none)

SortOrderParam = Annotated[Optional[ListSortOrder], BlankAsAbsent]
PromptBlockSearchParam = Annotated[Optional[PromptBlockSearchField], BlankAsAbsent]
PromptBlockSortParam = Annotated[Optional[PromptBlockSortField], BlankAsAbsent]
PromptTemplateSearchParam = Annotated[
    Optional[PromptTemplateSearchField], BlankAsAbsent
]
PromptTemplateSortParam = Annotated[Optional[PromptTemplateSortField], BlankAsAbsent]
CategorySortParam = Annotated[Optional[CategorySortField], BlankAsAbsent]

#: Every declared vocabulary, keyed by the route prefix that honours it.
LIST_VOCABULARIES: dict[str, ListVocabulary] = {
    vocabulary.resource: vocabulary
    for vocabulary in (
        PROMPT_BLOCK_LIST_VOCABULARY,
        PROMPT_TEMPLATE_LIST_VOCABULARY,
        CATEGORY_LIST_VOCABULARY,
    )
}
