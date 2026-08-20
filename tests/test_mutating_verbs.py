"""`C5`/`C17` — the two state-mutating routes answer *only* on a mutating verb.

`H3`: attaching a block to a template and moving one both changed state behind
a ``GET``. A ``GET`` is cacheable, prefetchable and link-followable, and the
``X-Requested-With`` header the client sends is not a defence on one — a
prefetching browser, a link-scanning mail client or an intermediary cache can
each fire it without a user ever acting.

`C5` shipped ``POST``/``PUT`` and kept the ``GET`` forms as deprecated aliases
so a consumer released before the change was not broken mid-flight. `C17`
removed them: `2.0.0` was never published, so no released consumer ever met
the aliases, and deleting them before the tag costs nothing while deleting
them after it would be a breaking change in a minor.

The removal is asserted as well as the replacement — a mutating ``GET`` that
comes back is the defect returning, and only a negative test can see that.
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
# The removed `GET` forms.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("url_for", [add_url, position_url], ids=["add", "move"])
def test_the_get_forms_no_longer_answer(
    client, headers, template_and_blocks, url_for
) -> None:
    """`C17`: the alias is gone from the router, not merely discouraged.

    ``405`` rather than ``404`` is the correct expectation — the path is still
    mounted, on the mutating verb alone — and it is the answer that
    distinguishes a removed alias from a mistyped path.
    """
    template, blocks = template_and_blocks

    response = client.get(url_for(template.id, blocks[0].id), headers=headers)

    assert response.status_code == 405, response.text
    assert attached(client, headers, template.id) == []


def test_the_get_forms_are_absent_from_the_schema(client) -> None:
    """The removal is published, not only implemented.

    A consumer's contract-drift check reads the OpenAPI document; a route the
    document still advertises is a route a generated client will still call.
    """
    paths = client.get(f"{PREFIX}/openapi.json").json()["paths"]
    add = paths[f"{PREFIX}/prompt-template/{{template_id}}/add-block/{{block_id}}/"]
    move = paths[
        f"{PREFIX}/prompt-template/{{template_id}}/set-block-position/{{block_id}}/"
    ]

    assert set(add) == {"post"}
    assert set(move) == {"put"}
    assert add["post"].get("deprecated", False) is False
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


@pytest.mark.parametrize(
    ("method", "url_for"),
    [("post", add_url), ("put", position_url)],
    ids=["add", "move"],
)
def test_the_writer_floor_is_enforced_on_both_verbs(
    client, auth_headers, template_and_blocks, method, url_for
) -> None:
    template, blocks = template_and_blocks
    response = client.request(
        method, url_for(template.id, blocks[0].id), headers=auth_headers("reader")
    )
    assert response.status_code == 403
