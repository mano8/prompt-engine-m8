"""`C4` — `POST /category/add/`, asserted over HTTP for the first time.

`H2`: the client posts `{name}` and the service requires `{name, type}`, so
every category create from the UI is a 422. The defect survived 100% coverage
on both sides because neither side ever crossed the boundary — the client test
mocks transport, and the service's only category-create test calls
``create_item(...)`` in-process with a ``CategoryCreate`` that already carries
``type``. A model constructed in the test cannot disagree with the model the
route validates against.

`D-C1` is resolved client-side: the service keeps requiring ``type``, and
`C9` teaches `astro-prompt-m8` to send it. A server-side default would make
every create succeed by guessing which of two category kinds the user meant —
a guess wearing a contract's clothes. The tests below pin the requirement so
the client half has something fixed to ship against.
"""

from __future__ import annotations

import uuid

import pytest

from promt_engine_service.core.config import settings
from promt_engine_service.db_models.categories import Category
from promt_engine_service.schemas.base import CategoryType

ADD = f"{settings.API_PREFIX}/category/add/"


def field_names(response) -> list[list[str]]:
    return [error["loc"] for error in response.json()["detail"]]


def test_the_payload_the_client_sends_today_is_rejected(client, auth_headers) -> None:
    """`H2`, at the boundary: `{name}` alone is a 422, and says which field."""
    response = client.post(
        ADD, headers=auth_headers("writer"), json={"name": "Wr1t1ng"}
    )

    assert response.status_code == 422, response.text
    assert ["body", "type"] in field_names(response)


def test_the_full_payload_succeeds_and_derives_the_slug(
    client, auth_headers, session
) -> None:
    owner = uuid.uuid4()
    response = client.post(
        ADD,
        headers=auth_headers("writer", owner),
        json={"name": "Writing Aids", "type": CategoryType.PROMPT_BLOCK.value},
    )

    assert response.status_code == 200, response.text
    created = response.json()["data"]
    assert created["slug"] == "writing-aids"
    assert created["type"] == CategoryType.PROMPT_BLOCK.value
    assert created["owner_id"] == str(owner)
    assert session.get(Category, created["id"]) is not None


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Bad", "type": "prompt_blocks"},
        {"name": "Bad", "type": ""},
        {"name": "", "type": CategoryType.PROMPT_BLOCK.value},
        {"type": CategoryType.PROMPT_BLOCK.value},
    ],
)
def test_an_invalid_payload_is_rejected(client, auth_headers, payload) -> None:
    response = client.post(ADD, headers=auth_headers("writer"), json=payload)
    assert response.status_code == 422, response.text


def test_a_caller_supplied_slug_does_not_win(client, auth_headers) -> None:
    """The slug is derived from the name, so two clients cannot disagree on it."""
    response = client.post(
        ADD,
        headers=auth_headers("writer"),
        json={
            "name": "Writing Aids",
            "slug": "something-else",
            "type": CategoryType.PROMPT_BLOCK.value,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["slug"] == "writing-aids"


def test_a_caller_cannot_file_a_category_under_another_owner(
    client, auth_headers
) -> None:
    """``owner_id`` comes from the token, never from the body.

    ``CategoryCreate`` does not declare the field, so a posted one is dropped
    before validation and the route's ``update=`` wins. Asserted rather than
    assumed: this is the difference between an ignored field and an ownership
    bypass.
    """
    caller = uuid.uuid4()
    victim = uuid.uuid4()
    response = client.post(
        ADD,
        headers=auth_headers("writer", caller),
        json={
            "name": "Writing Aids",
            "type": CategoryType.PROMPT_BLOCK.value,
            "owner_id": str(victim),
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["owner_id"] == str(caller)


def test_the_writer_floor_is_enforced_on_create(client, auth_headers) -> None:
    response = client.post(
        ADD,
        headers=auth_headers("reader"),
        json={"name": "Writing Aids", "type": CategoryType.PROMPT_BLOCK.value},
    )
    assert response.status_code == 403
