"""`C5` — the two state-mutating routes answer on a mutating verb.

`H3`: attaching a block to a template and moving one both changed state behind
a ``GET``. A ``GET`` is cacheable, prefetchable and link-followable, and the
``X-Requested-With`` header the client sends is not a defence on one — a
prefetching browser, a link-scanning mail client or an intermediary cache can
each fire it without a user ever acting.

The fix is additive: ``POST``/``PUT`` are the real verbs, and the ``GET``
forms stay mounted and marked deprecated for one minor so a consumer released
before this change is not broken mid-flight. Both are asserted, including that
they produce the same result — an alias that has drifted from its replacement
is worse than no alias.
"""

from __future__ import annotations

import uuid

import pytest

from promt_engine_service.core.config import settings
from promt_engine_service.db_models.prompts import PromptBlock, PromptTemplate
from promt_engine_service.schemas.base import PromptBlockType

PREFIX = settings.API_PREFIX


@pytest.fixture
def owner_uuid() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def headers(auth_headers, owner_uuid):
    return auth_headers("writer", owner_uuid)


@pytest.fixture
def template_and_blocks(session, owner_uuid):
    """One template and three unattached blocks, all owned by the caller."""
    template = PromptTemplate(name="Tpl", slug="tpl", owner_id=owner_uuid)
    blocks = [
        PromptBlock(
            name=f"Block {index}",
            slug=f"block-{index}",
            content="body",
            type=PromptBlockType.TASK,
            owner_id=owner_uuid,
        )
        for index in range(3)
    ]
    session.add_all([template, *blocks])
    session.commit()
    session.refresh(template)
    for block in blocks:
        session.refresh(block)
    return template, blocks


def add_url(template_id: int, block_id: int) -> str:
    return f"{PREFIX}/prompt-template/{template_id}/add-block/{block_id}/"


def position_url(template_id: int, block_id: int) -> str:
    return f"{PREFIX}/prompt-template/{template_id}/set-block-position/{block_id}/"


def attached(client, headers, template_id: int) -> list[str]:
    body = client.get(
        f"{PREFIX}/prompt-template/get-blocks/{template_id}/", headers=headers
    ).json()
    # The route reports an empty template as a message, not an empty list.
    return [item["slug"] for item in body.get("data", [])]


# --------------------------------------------------------------------------
# The real verbs.
# --------------------------------------------------------------------------


def test_a_block_is_attached_with_post(client, headers, template_and_blocks) -> None:
    template, blocks = template_and_blocks

    response = client.post(add_url(template.id, blocks[0].id), headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["block_id"] == blocks[0].id
    assert attached(client, headers, template.id) == ["block-0"]


def test_a_block_is_moved_with_put(client, headers, template_and_blocks) -> None:
    template, blocks = template_and_blocks
    for block in blocks:
        client.post(add_url(template.id, block.id), headers=headers)
    assert attached(client, headers, template.id) == ["block-0", "block-1", "block-2"]

    response = client.put(
        position_url(template.id, blocks[2].id),
        params={"position": 1},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert attached(client, headers, template.id) == ["block-2", "block-0", "block-1"]


# --------------------------------------------------------------------------
# The deprecated aliases.
# --------------------------------------------------------------------------


def test_the_get_aliases_still_work(client, headers, template_and_blocks) -> None:
    """A consumer released before `C5` keeps working for one more minor."""
    template, blocks = template_and_blocks

    added = client.get(add_url(template.id, blocks[0].id), headers=headers)
    client.get(add_url(template.id, blocks[1].id), headers=headers)
    moved = client.get(
        position_url(template.id, blocks[1].id),
        params={"position": 1},
        headers=headers,
    )

    assert added.status_code == 200, added.text
    assert moved.status_code == 200, moved.text
    assert attached(client, headers, template.id) == ["block-1", "block-0"]


def test_both_verbs_produce_the_same_result(
    client, headers, session, owner_uuid, template_and_blocks
) -> None:
    """The alias delegates rather than duplicating, so it cannot drift."""
    template, blocks = template_and_blocks
    other = PromptTemplate(name="Other", slug="other", owner_id=owner_uuid)
    session.add(other)
    session.commit()
    session.refresh(other)

    via_post = client.post(add_url(template.id, blocks[0].id), headers=headers).json()
    via_get = client.get(add_url(other.id, blocks[0].id), headers=headers).json()

    assert via_post["success"] == via_get["success"] is True
    assert via_post["data"]["position"] == via_get["data"]["position"] == 1
    assert via_post["data"]["block_id"] == via_get["data"]["block_id"]


def test_the_get_forms_are_marked_deprecated_in_the_schema(client) -> None:
    """The deprecation is published, not only intended.

    A consumer's contract-drift check reads the OpenAPI document; a route
    deprecated in a CHANGELOG alone is deprecated to nobody.
    """
    paths = client.get(f"{PREFIX}/openapi.json").json()["paths"]
    add = paths[f"{PREFIX}/prompt-template/{{template_id}}/add-block/{{block_id}}/"]
    move = paths[
        f"{PREFIX}/prompt-template/{{template_id}}/set-block-position/{{block_id}}/"
    ]

    assert add["get"]["deprecated"] is True
    assert add["post"].get("deprecated", False) is False
    assert move["get"]["deprecated"] is True
    assert move["put"].get("deprecated", False) is False


def test_the_delete_verb_is_unchanged(client, headers, template_and_blocks) -> None:
    """``DELETE .../delete-block/...`` was already correct and stays so."""
    template, blocks = template_and_blocks
    client.post(add_url(template.id, blocks[0].id), headers=headers)

    response = client.delete(
        f"{PREFIX}/prompt-template/{template.id}/delete-block/{blocks[0].id}/",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert attached(client, headers, template.id) == []


@pytest.mark.parametrize("method", ["post", "get"])
def test_the_writer_floor_is_enforced_on_both_verbs(
    client, auth_headers, template_and_blocks, method
) -> None:
    template, blocks = template_and_blocks
    response = client.request(
        method, add_url(template.id, blocks[0].id), headers=auth_headers("reader")
    )
    assert response.status_code == 403
