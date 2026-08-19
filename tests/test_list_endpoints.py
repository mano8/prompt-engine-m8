"""`C2`/`C3` — the list endpoints honour the declared vocabulary over HTTP.

Everything here goes through the real app, because the layer under test *is*
the HTTP layer: query-string parsing, enum coercion and FastAPI's own ``422``
are what turn a declared vocabulary into a contract. A test that called the
handler in-process would assert the handler agrees with itself.

The load-bearing case is :func:`test_filtering_crosses_the_page_boundary`. A
client that fetches one page and filters it in the browser passes every
single-page test ever written and is wrong the moment the data outgrows that
page; only a filter applied across pages tells the two implementations apart.
"""

from __future__ import annotations

import uuid

import pytest

from promt_engine_service.core.config import settings
from promt_engine_service.db_models.categories import Category
from promt_engine_service.db_models.prompts import (
    PromptBlock,
    PromptTemplate,
    TemplateBlock,
)
from promt_engine_service.schemas.base import CategoryType, PromptBlockType

PREFIX = settings.API_PREFIX
BLOCKS = f"{PREFIX}/prompt-block/"
TEMPLATES = f"{PREFIX}/prompt-template/"
CATEGORIES = f"{PREFIX}/category/"


@pytest.fixture
def owner_uuid() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def headers(auth_headers, owner_uuid):
    """A writer who owns every seeded record, so visibility is never the variable."""
    return auth_headers("writer", owner_uuid)


@pytest.fixture
def seeded_blocks(session, owner_uuid) -> None:
    """Four blocks spanning both boolean axes and three types."""
    session.add_all(
        [
            PromptBlock(
                name="Alpha reviewer",
                slug="alpha-reviewer",
                description="reviews things",
                content="you are a reviewer",
                type=PromptBlockType.ROLE,
                is_dynamic=False,
                is_public=True,
                owner_id=owner_uuid,
            ),
            PromptBlock(
                name="Beta summariser",
                slug="beta-summariser",
                description="summarises things",
                content="summarise the input",
                type=PromptBlockType.TASK,
                is_dynamic=True,
                is_public=False,
                owner_id=owner_uuid,
            ),
            PromptBlock(
                name="Gamma format",
                slug="gamma-format",
                description=None,
                content="answer as JSON",
                type=PromptBlockType.FORMAT,
                is_dynamic=False,
                is_public=False,
                owner_id=owner_uuid,
            ),
            PromptBlock(
                name="Delta context",
                slug="delta-context",
                description="alpha appears only here",
                content="background material",
                type=PromptBlockType.CONTEXT,
                is_dynamic=True,
                is_public=True,
                owner_id=owner_uuid,
            ),
        ]
    )
    session.commit()


def slugs(payload) -> list[str]:
    return [item["slug"] for item in payload["data"]]


# --------------------------------------------------------------------------
# The default response is the one `skip`/`limit` always produced.
# --------------------------------------------------------------------------


def test_absent_parameters_leave_the_offset_contract_untouched(
    client, headers, seeded_blocks
) -> None:
    body = client.get(BLOCKS, headers=headers).json()
    assert body["count"] == 4
    assert len(body["data"]) == 4

    paged = client.get(BLOCKS, params={"skip": 2, "limit": 2}, headers=headers).json()
    assert len(paged["data"]) == 2
    assert paged["count"] == 4


@pytest.mark.parametrize("param", ["q", "csrc", "sort", "order", "f"])
def test_a_blank_parameter_reads_as_an_absent_one(
    client, headers, seeded_blocks, param
) -> None:
    """Table controls send their unset state as an empty string, not by omitting."""
    body = client.get(BLOCKS, params={param: ""}, headers=headers).json()
    assert body["count"] == 4


# --------------------------------------------------------------------------
# Search.
# --------------------------------------------------------------------------


def test_q_searches_every_declared_column_and_filters_the_count(
    client, headers, seeded_blocks
) -> None:
    body = client.get(BLOCKS, params={"q": "alpha"}, headers=headers).json()

    # "Alpha reviewer" by name, "Delta context" by description.
    assert sorted(slugs(body)) == ["alpha-reviewer", "delta-context"]
    assert body["count"] == 2, "count must describe the filtered set, not the table"


def test_q_is_case_insensitive(client, headers, seeded_blocks) -> None:
    lowered = client.get(BLOCKS, params={"q": "gamma"}, headers=headers).json()
    upper = client.get(BLOCKS, params={"q": "GAMMA"}, headers=headers).json()
    assert slugs(lowered) == slugs(upper) == ["gamma-format"]


def test_csrc_restricts_the_search_to_one_column(
    client, headers, seeded_blocks
) -> None:
    everywhere = client.get(BLOCKS, params={"q": "alpha"}, headers=headers).json()
    by_name = client.get(
        BLOCKS, params={"q": "alpha", "csrc": "name"}, headers=headers
    ).json()

    assert len(everywhere["data"]) == 2
    assert slugs(by_name) == ["alpha-reviewer"]
    assert by_name["count"] == 1


def test_wildcards_in_q_are_matched_literally(client, headers, seeded_blocks) -> None:
    """``%`` is escaped, so it cannot widen a search into "everything"."""
    body = client.get(BLOCKS, params={"q": "%"}, headers=headers).json()
    assert body["count"] == 0


# --------------------------------------------------------------------------
# Facets.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("facet", "expected"),
    [
        ("role", ["alpha-reviewer"]),
        ("public", ["alpha-reviewer", "delta-context"]),
        ("private", ["beta-summariser", "gamma-format"]),
        ("dynamic", ["beta-summariser", "delta-context"]),
        ("static", ["alpha-reviewer", "gamma-format"]),
    ],
)
def test_a_single_facet_filters_and_counts(
    client, headers, seeded_blocks, facet, expected
) -> None:
    body = client.get(BLOCKS, params={"f": facet}, headers=headers).json()
    assert sorted(slugs(body)) == expected
    assert body["count"] == len(expected)


def test_several_facets_combine_with_or(client, headers, seeded_blocks) -> None:
    """Matching the faceted-filter control, which widens rather than narrows."""
    body = client.get(BLOCKS, params={"f": "role,format"}, headers=headers).json()
    assert sorted(slugs(body)) == ["alpha-reviewer", "gamma-format"]


def test_search_and_facets_combine_with_and(client, headers, seeded_blocks) -> None:
    body = client.get(
        BLOCKS, params={"q": "alpha", "f": "public"}, headers=headers
    ).json()
    assert sorted(slugs(body)) == ["alpha-reviewer", "delta-context"]

    narrowed = client.get(
        BLOCKS, params={"q": "alpha", "f": "static"}, headers=headers
    ).json()
    assert slugs(narrowed) == ["alpha-reviewer"]


# --------------------------------------------------------------------------
# Sorting.
# --------------------------------------------------------------------------


def test_sort_and_order_are_honoured(client, headers, seeded_blocks) -> None:
    ascending = client.get(BLOCKS, params={"sort": "name"}, headers=headers).json()
    descending = client.get(
        BLOCKS, params={"sort": "name", "order": "desc"}, headers=headers
    ).json()

    assert slugs(ascending) == [
        "alpha-reviewer",
        "beta-summariser",
        "delta-context",
        "gamma-format",
    ]
    assert slugs(descending) == list(reversed(slugs(ascending)))


def test_sort_without_order_ascends(client, headers, seeded_blocks) -> None:
    body = client.get(BLOCKS, params={"sort": "slug"}, headers=headers).json()
    assert slugs(body) == sorted(slugs(body))


# --------------------------------------------------------------------------
# Rejection — an undeclared value is refused, never quietly dropped.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {"sort": "owner_id"},
        {"sort": "name; DROP TABLE app_prompt_blocks"},
        {"csrc": "owner_id"},
        {"order": "sideways"},
        {"f": "unknown"},
        {"f": "public,unknown"},
        {"skip": -1},
        {"limit": 0},
        {"q": "x" * 201},
    ],
)
def test_an_undeclared_value_is_rejected(
    client, headers, seeded_blocks, params
) -> None:
    response = client.get(BLOCKS, params=params, headers=headers)
    assert response.status_code == 422, response.text


def test_a_rejected_filter_returns_no_rows_at_all(
    client, headers, seeded_blocks
) -> None:
    """The alternative — ignoring the filter — would return *every* row.

    That is the shape of the original defect: a control that appears to work,
    over a result set it never touched.
    """
    response = client.get(BLOCKS, params={"f": "unknown"}, headers=headers)
    assert response.status_code == 422
    assert "data" not in response.json()


# --------------------------------------------------------------------------
# The page-boundary proof.
# --------------------------------------------------------------------------


def test_filtering_crosses_the_page_boundary(client, headers, session, owner_uuid):
    """25 blocks, 10 per page, a filter matching 5 spread across all three pages.

    Client-side filtering of the first page would find 2 of them and report a
    count of 2. Only a server that filters *before* paginating answers 5.
    """
    session.add_all(
        [
            PromptBlock(
                name=f"Block {index:02d}",
                slug=f"block-{index:02d}",
                content="body",
                type=PromptBlockType.TASK,
                is_public=index % 5 == 0,
                owner_id=owner_uuid,
            )
            for index in range(25)
        ]
    )
    session.commit()

    first = client.get(
        BLOCKS,
        params={"f": "public", "sort": "slug", "skip": 0, "limit": 10},
        headers=headers,
    ).json()

    assert first["count"] == 5
    assert slugs(first) == [
        "block-00",
        "block-05",
        "block-10",
        "block-15",
        "block-20",
    ]

    unfiltered = client.get(BLOCKS, params={"limit": 10}, headers=headers).json()
    assert unfiltered["count"] == 25


# --------------------------------------------------------------------------
# Templates.
# --------------------------------------------------------------------------


@pytest.fixture
def seeded_templates(session, owner_uuid) -> None:
    """Three templates carrying 2, 1 and 0 blocks."""
    blocks = [
        PromptBlock(
            name=f"Block {index}",
            slug=f"tpl-block-{index}",
            content="body",
            type=PromptBlockType.TASK,
            owner_id=owner_uuid,
        )
        for index in range(2)
    ]
    session.add_all(blocks)
    session.commit()
    for block in blocks:
        session.refresh(block)

    templates = [
        PromptTemplate(
            name="Wide",
            slug="wide",
            description="two blocks",
            is_public=True,
            owner_id=owner_uuid,
        ),
        PromptTemplate(
            name="Narrow",
            slug="narrow",
            description="one block",
            is_public=False,
            owner_id=owner_uuid,
        ),
        PromptTemplate(
            name="Empty",
            slug="empty",
            description="no blocks",
            is_public=True,
            owner_id=owner_uuid,
        ),
    ]
    session.add_all(templates)
    session.commit()
    for template in templates:
        session.refresh(template)

    session.add_all(
        [
            TemplateBlock(
                template_id=templates[0].id, block_id=blocks[0].id, position=1
            ),
            TemplateBlock(
                template_id=templates[0].id, block_id=blocks[1].id, position=2
            ),
            TemplateBlock(
                template_id=templates[1].id, block_id=blocks[0].id, position=1
            ),
        ]
    )
    session.commit()


def test_template_search_and_facets(client, headers, seeded_templates) -> None:
    searched = client.get(TEMPLATES, params={"q": "one block"}, headers=headers).json()
    faceted = client.get(TEMPLATES, params={"f": "private"}, headers=headers).json()

    assert slugs(searched) == ["narrow"]
    assert searched["count"] == 1
    assert slugs(faceted) == ["narrow"]
    assert faceted["count"] == 1


def test_templates_sort_by_block_count_in_sql(
    client, headers, seeded_templates
) -> None:
    """The one declared sort that is a subquery rather than a column."""
    ascending = client.get(
        TEMPLATES, params={"sort": "block_count"}, headers=headers
    ).json()
    descending = client.get(
        TEMPLATES, params={"sort": "block_count", "order": "desc"}, headers=headers
    ).json()

    assert slugs(ascending) == ["empty", "narrow", "wide"]
    assert slugs(descending) == ["wide", "narrow", "empty"]


def test_template_csrc_restricts_the_search(client, headers, seeded_templates) -> None:
    everywhere = client.get(TEMPLATES, params={"q": "wide"}, headers=headers).json()
    by_description = client.get(
        TEMPLATES, params={"q": "wide", "csrc": "description"}, headers=headers
    ).json()

    assert slugs(everywhere) == ["wide"]
    assert by_description["count"] == 0


@pytest.mark.parametrize(
    "params", [{"sort": "owner_id"}, {"csrc": "content"}, {"f": "dynamic"}]
)
def test_the_template_vocabulary_is_its_own(
    client, headers, seeded_templates, params
) -> None:
    """A block value is not a template value: ``content`` and ``dynamic``
    exist on blocks and nowhere else, so the template endpoint refuses them."""
    assert client.get(TEMPLATES, params=params, headers=headers).status_code == 422


# --------------------------------------------------------------------------
# Categories (`C3`).
# --------------------------------------------------------------------------


@pytest.fixture
def seeded_categories(session, owner_uuid) -> None:
    session.add_all(
        [
            Category(
                name="Writing",
                slug="writing",
                type=CategoryType.PROMPT_BLOCK,
                owner_id=owner_uuid,
            ),
            Category(
                name="Review",
                slug="review",
                type=CategoryType.PROMPT_TEMPLATE,
                owner_id=owner_uuid,
            ),
            Category(
                name="Analysis",
                slug="analysis",
                type=CategoryType.PROMPT_BLOCK,
                owner_id=owner_uuid,
            ),
        ]
    )
    session.commit()


def test_category_search_filters_and_counts(client, headers, seeded_categories) -> None:
    body = client.get(CATEGORIES, params={"q": "review"}, headers=headers).json()
    assert slugs(body) == ["review"]
    assert body["count"] == 1


def test_category_sort_and_order(client, headers, seeded_categories) -> None:
    ascending = client.get(CATEGORIES, params={"sort": "name"}, headers=headers).json()
    descending = client.get(
        CATEGORIES, params={"sort": "name", "order": "desc"}, headers=headers
    ).json()

    assert slugs(ascending) == ["analysis", "review", "writing"]
    assert slugs(descending) == ["writing", "review", "analysis"]


def test_category_visibility_split_survives_the_new_parameters(
    client, auth_headers, session, owner_uuid, seeded_categories
) -> None:
    """Filtering must not widen what a non-superuser can see.

    The owner-vs-superuser split predates this contract; a search that returned
    another user's category would be a far worse defect than the missing search
    it replaced.
    """
    session.add(
        Category(
            name="Stranger review",
            slug="stranger-review",
            type=CategoryType.PROMPT_BLOCK,
            owner_id=uuid.uuid4(),
        )
    )
    session.commit()

    owned = client.get(
        CATEGORIES, params={"q": "review"}, headers=auth_headers("writer", owner_uuid)
    ).json()
    everything = client.get(
        CATEGORIES,
        params={"q": "review"},
        headers=auth_headers("superadmin", is_superuser=True),
    ).json()

    assert slugs(owned) == ["review"]
    assert owned["count"] == 1
    assert sorted(slugs(everything)) == ["review", "stranger-review"]
    assert everything["count"] == 2


@pytest.mark.parametrize("params", [{"sort": "owner_id"}, {"order": "sideways"}])
def test_undeclared_category_values_are_rejected(
    client, headers, seeded_categories, params
) -> None:
    assert client.get(CATEGORIES, params=params, headers=headers).status_code == 422


def test_the_category_endpoint_declares_no_csrc_or_facets(
    client, headers, seeded_categories
) -> None:
    """Undeclared *parameters* are ignored by FastAPI rather than rejected.

    That is framework behaviour, not a contract hole — the point of the empty
    tuples in ``CATEGORY_LIST_VOCABULARY`` is that a client never sends these.
    Asserted so the day the endpoint grows them, this test is what changes.
    """
    body = client.get(
        CATEGORIES, params={"csrc": "name", "f": "public"}, headers=headers
    ).json()
    assert body["count"] == 3
