"""`C1` — the declared list vocabulary is the whole allow-list, and it is SQL-safe.

Two properties are asserted here, because either one alone is a false comfort:

* **The declaration and the mapping are the same set.** A name declared in
  ``schemas.list_params`` with no column behind it is a ``KeyError`` in
  production; a column reachable through ``controllers.prompts`` without being
  declared is an undocumented parameter. Both directions are checked, for all
  three resources.
* **Nothing a caller sends is interpolated.** ``sort``/``csrc``/``f`` are
  resolved through a mapping to column objects and are rejected otherwise;
  ``q`` reaches the statement as a bound parameter. The compiled SQL is
  inspected rather than trusted.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from promt_engine_service.controllers.prompts import ListQueryController
from promt_engine_service.db_models.categories import Category
from promt_engine_service.db_models.prompts import PromptBlock, PromptTemplate
from promt_engine_service.schemas.base import PromptBlockType
from promt_engine_service.schemas.list_params import (
    CATEGORY_LIST_VOCABULARY,
    PROMPT_BLOCK_LIST_VOCABULARY,
    PROMPT_TEMPLATE_LIST_VOCABULARY,
    CategorySearchField,
    CategorySortField,
    ListSortOrder,
    ListVocabulary,
    PromptBlockFacet,
    PromptBlockSearchField,
    PromptBlockSortField,
    PromptTemplateFacet,
    PromptTemplateSearchField,
    PromptTemplateSortField,
)

# resource, vocabulary, csrc enum, sort enum, facet enum, mapped csrc/sort/facet
RESOURCES = [
    pytest.param(
        PROMPT_BLOCK_LIST_VOCABULARY,
        PromptBlockSearchField,
        PromptBlockSortField,
        PromptBlockFacet,
        ListQueryController.BLOCK_SEARCH_COLUMNS,
        ListQueryController.BLOCK_SORT_COLUMNS,
        ListQueryController.BLOCK_FACET_PREDICATES,
        id="prompt-block",
    ),
    pytest.param(
        PROMPT_TEMPLATE_LIST_VOCABULARY,
        PromptTemplateSearchField,
        PromptTemplateSortField,
        PromptTemplateFacet,
        ListQueryController.TEMPLATE_SEARCH_COLUMNS,
        ListQueryController.TEMPLATE_SORT_COLUMNS,
        ListQueryController.TEMPLATE_FACET_PREDICATES,
        id="prompt-template",
    ),
]


@pytest.mark.parametrize(
    (
        "vocabulary",
        "search_enum",
        "sort_enum",
        "facet_enum",
        "search_columns",
        "sort_columns",
        "facet_predicates",
    ),
    RESOURCES,
)
def test_declared_vocabulary_and_mapping_are_the_same_set(
    vocabulary: ListVocabulary,
    search_enum,
    sort_enum,
    facet_enum,
    search_columns,
    sort_columns,
    facet_predicates,
) -> None:
    assert vocabulary.csrc == tuple(member.value for member in search_enum)
    assert vocabulary.sort == tuple(member.value for member in sort_enum)
    assert vocabulary.facets == tuple(member.value for member in facet_enum)
    assert vocabulary.q_columns == vocabulary.csrc

    assert set(search_columns) == set(search_enum)
    assert set(sort_columns) == set(sort_enum)
    assert set(facet_predicates) == set(facet_enum)


def test_category_vocabulary_and_mapping_are_the_same_set() -> None:
    """The category endpoint offers no ``csrc`` and no facets — by declaration.

    Empty tuples are the contract saying "this endpoint does not take that
    parameter", so they are asserted rather than left implied.
    """
    assert CATEGORY_LIST_VOCABULARY.q_columns == tuple(
        member.value for member in CategorySearchField
    )
    assert CATEGORY_LIST_VOCABULARY.sort == tuple(
        member.value for member in CategorySortField
    )
    assert CATEGORY_LIST_VOCABULARY.csrc == ()
    assert CATEGORY_LIST_VOCABULARY.facets == ()
    assert set(ListQueryController.CATEGORY_SEARCH_COLUMNS) == set(CategorySearchField)
    assert set(ListQueryController.CATEGORY_SORT_COLUMNS) == set(CategorySortField)


def test_every_block_type_is_a_declared_block_facet() -> None:
    """The type facets mirror ``PromptBlockType`` exactly.

    A block type added to the domain without a facet would be filterable in
    principle and unreachable in practice.
    """
    facets = {member.value for member in PromptBlockFacet}
    assert {member.value for member in PromptBlockType} <= facets
    assert facets - {member.value for member in PromptBlockType} == {
        "dynamic",
        "static",
        "public",
        "private",
    }


@pytest.mark.parametrize(
    ("columns", "model"),
    [
        (ListQueryController.BLOCK_SEARCH_COLUMNS, PromptBlock),
        (ListQueryController.BLOCK_SORT_COLUMNS, PromptBlock),
        (ListQueryController.TEMPLATE_SEARCH_COLUMNS, PromptTemplate),
        (ListQueryController.CATEGORY_SEARCH_COLUMNS, Category),
        (ListQueryController.CATEGORY_SORT_COLUMNS, Category),
    ],
)
def test_every_mapped_name_resolves_to_a_column_on_its_own_model(
    columns, model
) -> None:
    """Each mapping value is the identically-named column of its own model.

    Both halves matter: a declared name pointing at some *other* column would
    satisfy a weaker "is a column" check while quietly sorting by the wrong
    thing.

    ``block_count`` is deliberately excluded from this matrix: it is the one
    declared sort that is a subquery rather than a column, and it is covered by
    its own ordering test.
    """
    table_columns = model.__table__.columns
    for name, column in columns.items():
        assert name.value in table_columns, name
        assert column.key == name.value


def test_block_count_sort_is_a_scalar_subquery_over_template_blocks() -> None:
    clause = ListQueryController.order_clause(
        ListQueryController.TEMPLATE_SORT_COLUMNS,
        PromptTemplateSortField.BLOCK_COUNT,
        ListSortOrder.ASC,
    )
    rendered = str(clause)
    assert "count(" in rendered
    assert "template_blocks" in rendered


# --------------------------------------------------------------------------
# Allow-listed in, everything else out.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("facet", list(PromptBlockFacet))
def test_every_declared_block_facet_is_accepted(facet: PromptBlockFacet) -> None:
    assert ListQueryController.parse_facets(
        facet.value, PromptBlockFacet, "prompt-block"
    ) == [facet]


@pytest.mark.parametrize(
    "raw", ["unknown", "public,unknown", "PUBLIC", "public;drop", "1"]
)
def test_an_undeclared_facet_value_is_rejected_not_ignored(raw: str) -> None:
    with pytest.raises(HTTPException) as rejected:
        ListQueryController.parse_facets(raw, PromptBlockFacet, "prompt-block")
    assert rejected.value.status_code == 422
    assert "prompt-block filter value" in rejected.value.detail


def test_empty_and_blank_segments_mean_no_filter() -> None:
    """The empty default a faceted-filter control sends is not an error."""
    for raw in ("", "   ", ",", " , "):
        assert (
            ListQueryController.parse_facets(raw, PromptBlockFacet, "prompt-block")
            == []
        )


def test_repeated_facets_are_deduplicated_in_declaration_order() -> None:
    assert ListQueryController.parse_facets(
        " public , dynamic , public ", PromptBlockFacet, "prompt-block"
    ) == [PromptBlockFacet.PUBLIC, PromptBlockFacet.DYNAMIC]


def test_no_facets_selected_yields_no_predicate() -> None:
    assert (
        ListQueryController.facet_predicate(
            [], ListQueryController.BLOCK_FACET_PREDICATES
        )
        is None
    )


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_a_blank_query_yields_no_search_predicate(blank: str) -> None:
    assert (
        ListQueryController.search_predicate(
            ListQueryController.BLOCK_SEARCH_COLUMNS, blank
        )
        is None
    )


def test_csrc_narrows_the_search_to_exactly_one_column() -> None:
    every_column = ListQueryController.search_predicate(
        ListQueryController.BLOCK_SEARCH_COLUMNS, "term"
    )
    one_column = ListQueryController.search_predicate(
        ListQueryController.BLOCK_SEARCH_COLUMNS,
        "term",
        PromptBlockSearchField.SLUG,
    )
    assert str(every_column).count("LIKE") == len(PromptBlockSearchField)
    assert str(one_column).count("LIKE") == 1
    assert "slug" in str(one_column)


def test_order_clause_follows_the_declared_direction() -> None:
    columns = ListQueryController.BLOCK_SORT_COLUMNS
    ascending = ListQueryController.order_clause(
        columns, PromptBlockSortField.NAME, ListSortOrder.ASC
    )
    descending = ListQueryController.order_clause(
        columns, PromptBlockSortField.NAME, ListSortOrder.DESC
    )
    assert str(ascending).endswith("ASC")
    assert str(descending).endswith("DESC")


# --------------------------------------------------------------------------
# `SEC-VALIDATE-UNTRUSTED-INPUT` — the term is bound, never interpolated.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "term",
    [
        "'; DROP TABLE app_prompt_blocks; --",
        "100% OR 1=1",
        "under_score",
        "back\\slash",
    ],
)
def test_the_search_term_never_reaches_the_sql_text(term: str) -> None:
    """Compiled SQL carries placeholders; the term lives in the parameters.

    ``contains(autoescape=True)`` also neutralises ``%`` and ``_`` with ``/``,
    so a term that looks like a wildcard is matched literally instead of
    widening the scan — asserted here by reproducing that escaping and
    demanding the bound value match it exactly.
    """
    escaped = term.lower().replace("/", "//").replace("%", "/%").replace("_", "/_")
    predicate = ListQueryController.search_predicate(
        ListQueryController.BLOCK_SEARCH_COLUMNS, term
    )
    compiled = predicate.compile()

    assert term.lower() not in str(compiled)
    assert set(compiled.params.values()) == {escaped}


# --------------------------------------------------------------------------
# The per-resource entry points the routes call.
# --------------------------------------------------------------------------


def test_block_predicates_combine_search_and_facets() -> None:
    both = ListQueryController.prompt_block_predicates(
        q="term", csrc=PromptBlockSearchField.NAME, f="public,dynamic"
    )
    search_only = ListQueryController.prompt_block_predicates(q="term", csrc=None, f="")
    facets_only = ListQueryController.prompt_block_predicates(
        q="", csrc=None, f="static"
    )
    neither = ListQueryController.prompt_block_predicates(q="  ", csrc=None, f="")

    assert len(both) == 2
    assert len(search_only) == 1
    assert len(facets_only) == 1
    assert neither == []


def test_template_predicates_combine_search_and_facets() -> None:
    both = ListQueryController.prompt_template_predicates(
        q="term", csrc=PromptTemplateSearchField.DESCRIPTION, f="private"
    )
    neither = ListQueryController.prompt_template_predicates(q="", csrc=None, f="")

    assert len(both) == 2
    assert neither == []


def test_category_predicates_search_the_declared_columns() -> None:
    """No ``csrc`` to narrow with, so ``q`` always scans both declared columns."""
    searching = ListQueryController.category_predicates(q="term")
    idle = ListQueryController.category_predicates(q="")

    assert len(searching) == 1
    assert str(searching[0]).count("LIKE") == len(CategorySearchField)
    assert idle == []
