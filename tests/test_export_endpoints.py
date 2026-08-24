"""`A-C8` — the unpaginated export reads over the filtered set.

`C7`/`C8` on `astro-prompt-m8` made the client's bulk-export buttons act on one
fetched page, because a server-driven table only ever holds one page. These
endpoints are the other half: a read with no `skip`/`limit` at all, so a
caller exporting a filtered set gets every matching row in one response
rather than the page the table happens to be showing.

The load-bearing case mirrors `test_filtering_crosses_the_page_boundary` in
`test_list_endpoints.py`: a filtered set larger than one page must come back
whole, not truncated to what a single list page would have held.
"""

from __future__ import annotations

import uuid

import pytest

from promt_engine_service.app.routes import prompt_blocks as prompt_blocks_routes
from promt_engine_service.app.routes import prompt_templates as prompt_templates_routes
from promt_engine_service.core.config import settings
from promt_engine_service.db_models.prompts import PromptBlock, PromptTemplate
from promt_engine_service.schemas.base import PromptBlockType

PREFIX = settings.API_PREFIX
BLOCKS_EXPORT = f"{PREFIX}/prompt-block/export/"
TEMPLATES_EXPORT = f"{PREFIX}/prompt-template/export/"


@pytest.fixture
def owner_uuid() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def headers(auth_headers, owner_uuid):
    return auth_headers("writer", owner_uuid)


def slugs(payload) -> list[str]:
    return [item["slug"] for item in payload["data"]]


def test_export_carries_no_skip_or_limit_and_returns_every_matching_row(
    client, headers, session, owner_uuid
) -> None:
    """25 blocks, a filter matching 5 spread across what would be three pages.

    A page-at-a-time export would return at most 10 of these (`limit`
    defaults to 100, but the point survives regardless); the export route has
    no `limit` parameter to default, so it returns all 5.
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

    body = client.get(
        BLOCKS_EXPORT, params={"f": "public", "sort": "slug"}, headers=headers
    ).json()

    assert body["count"] == 5
    assert body["truncated"] is False
    assert slugs(body) == [
        "block-00",
        "block-05",
        "block-10",
        "block-15",
        "block-20",
    ]


def test_export_honours_the_same_vocabulary_as_the_list_route(
    client, headers, session, owner_uuid
) -> None:
    session.add_all(
        [
            PromptBlock(
                name="Alpha reviewer",
                slug="alpha-reviewer",
                description="reviews things",
                content="you are a reviewer",
                type=PromptBlockType.ROLE,
                is_public=True,
                owner_id=owner_uuid,
            ),
            PromptBlock(
                name="Beta summariser",
                slug="beta-summariser",
                description="summarises things",
                content="summarise the input",
                type=PromptBlockType.TASK,
                is_public=False,
                owner_id=owner_uuid,
            ),
        ]
    )
    session.commit()

    body = client.get(
        BLOCKS_EXPORT, params={"q": "alpha", "csrc": "name"}, headers=headers
    ).json()
    assert slugs(body) == ["alpha-reviewer"]
    assert body["count"] == 1


@pytest.mark.parametrize(
    "params",
    [
        {"sort": "owner_id"},
        {"csrc": "owner_id"},
        {"order": "sideways"},
        {"f": "unknown"},
    ],
)
def test_export_rejects_an_undeclared_value(client, headers, params) -> None:
    response = client.get(BLOCKS_EXPORT, params=params, headers=headers)
    assert response.status_code == 422, response.text


def test_export_respects_visibility(client, auth_headers, session, owner_uuid) -> None:
    session.add_all(
        [
            PromptBlock(
                name="Mine",
                slug="mine",
                content="body",
                type=PromptBlockType.TASK,
                is_public=False,
                owner_id=owner_uuid,
            ),
            PromptBlock(
                name="Theirs",
                slug="theirs",
                content="body",
                type=PromptBlockType.TASK,
                is_public=False,
                owner_id=uuid.uuid4(),
            ),
        ]
    )
    session.commit()

    body = client.get(BLOCKS_EXPORT, headers=auth_headers("writer", owner_uuid)).json()
    assert slugs(body) == ["mine"]


def test_export_truncates_at_the_cap_rather_than_growing_unbounded(
    client, headers, session, owner_uuid, monkeypatch
) -> None:
    monkeypatch.setattr(prompt_blocks_routes, "MAX_EXPORT_SIZE", 3)
    session.add_all(
        [
            PromptBlock(
                name=f"Block {index}",
                slug=f"cap-block-{index}",
                content="body",
                type=PromptBlockType.TASK,
                owner_id=owner_uuid,
            )
            for index in range(5)
        ]
    )
    session.commit()

    body = client.get(BLOCKS_EXPORT, headers=headers).json()
    assert body["count"] == 5
    assert body["truncated"] is True
    assert len(body["data"]) == 3


# --------------------------------------------------------------------------
# Templates.
# --------------------------------------------------------------------------


@pytest.fixture
def seeded_templates(session, owner_uuid) -> None:
    session.add_all(
        [
            PromptTemplate(
                name="Wide",
                slug="wide",
                description="public",
                is_public=True,
                owner_id=owner_uuid,
            ),
            PromptTemplate(
                name="Narrow",
                slug="narrow",
                description="private",
                is_public=False,
                owner_id=owner_uuid,
            ),
        ]
    )
    session.commit()


def test_template_export_carries_the_template_vocabulary(
    client, headers, seeded_templates
) -> None:
    body = client.get(TEMPLATES_EXPORT, params={"f": "private"}, headers=headers).json()
    assert slugs(body) == ["narrow"]
    assert body["count"] == 1
    assert body["truncated"] is False


def test_template_export_rejects_a_block_only_value(client, headers) -> None:
    response = client.get(TEMPLATES_EXPORT, params={"f": "dynamic"}, headers=headers)
    assert response.status_code == 422


def test_template_export_truncates_at_the_cap(
    client, headers, session, owner_uuid, monkeypatch
) -> None:
    monkeypatch.setattr(prompt_templates_routes, "MAX_EXPORT_SIZE", 2)
    session.add_all(
        [
            PromptTemplate(
                name=f"Template {index}",
                slug=f"cap-template-{index}",
                owner_id=owner_uuid,
            )
            for index in range(4)
        ]
    )
    session.commit()

    body = client.get(TEMPLATES_EXPORT, headers=headers).json()
    assert body["count"] == 4
    assert body["truncated"] is True
    assert len(body["data"]) == 2
