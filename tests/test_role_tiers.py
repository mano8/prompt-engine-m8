"""A15 acceptance matrix — the role tiers are mounted, not merely intended.

Every case here goes through the real application: a real HS256 access token,
the real ``fastapi-m8`` validator, and the real ``auth.get_current_active_*``
guard mounted on the route. Nothing on the authorization path is stubbed — only
the database session is overridden — so a ``403`` observed below is the ``403``
a deployed service produces, and a ``200`` proves the guard admitted rather than
that a test forgot to install it.

The matrix the operator specified:

* ``WRITER`` and above — add, edit and delete owned records; dashboard.
* ``READER`` and above — owned lists and owned items.
* ``USER`` — public items only, nothing else.
"""

from __future__ import annotations

import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from promt_engine_service.core.config import settings
from promt_engine_service.core.deps import (
    get_db,
    require_admin,
    require_reader,
    require_writer,
)
from promt_engine_service.db_models.prompts import PromptBlock
from promt_engine_service.schemas.base import PromptBlockType

PREFIX = settings.API_PREFIX

# One route per tier, named once so the matrix below reads as a table.
PUBLIC_READ = ("GET", f"{PREFIX}/prompt-block/")
OWNED_READ = ("GET", f"{PREFIX}/category/")
MUTATION = ("POST", f"{PREFIX}/prompt-block/add/")
DASHBOARD = ("GET", f"{PREFIX}/dashboard/users/activity/")

NEW_BLOCK = {"name": "Fresh", "content": "content", "type": PromptBlockType.TASK.value}


def _token(role: str, user_id: uuid.UUID, *, is_superuser: bool = False) -> str:
    """Mint the access token the issuer would mint for *role*."""
    now = int(time.time())
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": "access",
            "jti": uuid.uuid4().hex,
            "iat": now,
            "exp": now + 600,
            "email": f"{role}@example.com",
            "role": role,
            "is_superuser": is_superuser,
        },
        settings.ACCESS_SECRET_KEY.get_secret_value(),
        algorithm=settings.ACCESS_TOKEN_ALGORITHM,
    )


def _auth(role: str, user_id: uuid.UUID | None = None, **kwargs) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token(role, user_id or uuid.uuid4(), **kwargs)}"
    }


@pytest.fixture
def client(session) -> TestClient:
    """The real app, with only the database session replaced.

    Constructed without the context manager on purpose: entering it would run
    the lifespan, which opens the configured Postgres engine and the auth event
    stream. Neither is on the authorization path this file is about.
    """
    import promt_engine_service.main as main

    main.app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(main.app)
    finally:
        main.app.dependency_overrides.clear()


@pytest.fixture
def seeded_blocks(session) -> dict[str, PromptBlock]:
    """One public block and one private block, both owned by a third party."""
    stranger = uuid.uuid4()
    public = PromptBlock(
        name="Public",
        slug="public",
        content="public content",
        type=PromptBlockType.TASK,
        owner_id=stranger,
        is_public=True,
    )
    private = PromptBlock(
        name="Private",
        slug="private",
        content="private content",
        type=PromptBlockType.TASK,
        owner_id=stranger,
        is_public=False,
    )
    session.add_all([public, private])
    session.commit()
    session.refresh(public)
    session.refresh(private)
    return {"public": public, "private": private}


# --------------------------------------------------------------------------
# Denial matrix — a principal below the route's floor is refused, with 403
# ("authenticated, wrong role"), never 401 ("no identity").
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "method", "path"),
    [
        ("user", *OWNED_READ),
        ("user", *MUTATION),
        ("user", *DASHBOARD),
        ("reader", *MUTATION),
        ("reader", *DASHBOARD),
    ],
)
def test_principal_below_the_floor_is_denied(client, role, method, path) -> None:
    response = client.request(method, path, headers=_auth(role), json=NEW_BLOCK)
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "The user doesn't have enough privileges"


@pytest.mark.parametrize(
    ("method", "path"), [PUBLIC_READ, OWNED_READ, MUTATION, DASHBOARD]
)
def test_every_route_requires_authentication(client, method, path) -> None:
    assert client.request(method, path, json=NEW_BLOCK).status_code == 401


# --------------------------------------------------------------------------
# Admission matrix — the same routes answer for a principal at or above the
# floor, so the denials above are the guard working and not the route broken.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "method", "path"),
    [
        ("user", *PUBLIC_READ),
        ("reader", *PUBLIC_READ),
        ("reader", *OWNED_READ),
        ("writer", *OWNED_READ),
        ("writer", *MUTATION),
        ("writer", *DASHBOARD),
        ("admin", *MUTATION),
    ],
)
def test_principal_at_or_above_the_floor_is_admitted(
    client, role, method, path
) -> None:
    response = client.request(method, path, headers=_auth(role), json=NEW_BLOCK)
    assert response.status_code == 200, response.text


# --------------------------------------------------------------------------
# Visibility — the USER tier's read surface is public records only.
# --------------------------------------------------------------------------


def test_user_tier_lists_public_records_only(client, seeded_blocks) -> None:
    body = client.get(PUBLIC_READ[1], headers=_auth("user")).json()
    assert [item["slug"] for item in body["data"]] == ["public"]
    assert body["count"] == 1


def test_user_tier_reads_a_public_record_and_is_denied_a_private_one(
    client, seeded_blocks
) -> None:
    headers = _auth("user")
    public_id = seeded_blocks["public"].id
    private_id = seeded_blocks["private"].id

    allowed = client.get(f"{PREFIX}/prompt-block/get/{public_id}/", headers=headers)
    assert allowed.status_code == 200, allowed.text
    denied = client.get(f"{PREFIX}/prompt-block/get/{private_id}/", headers=headers)
    assert denied.status_code == 403


def test_reader_tier_sees_its_own_records_plus_public_ones(
    client, session, seeded_blocks
) -> None:
    reader_id = uuid.uuid4()
    session.add(
        PromptBlock(
            name="Mine",
            slug="mine",
            content="mine",
            type=PromptBlockType.TASK,
            owner_id=reader_id,
            is_public=False,
        )
    )
    session.commit()

    body = client.get(PUBLIC_READ[1], headers=_auth("reader", reader_id)).json()
    assert sorted(item["slug"] for item in body["data"]) == ["mine", "public"]
    assert body["count"] == 2


def test_superuser_sees_every_record(client, seeded_blocks) -> None:
    body = client.get(
        PUBLIC_READ[1], headers=_auth("superadmin", is_superuser=True)
    ).json()
    assert sorted(item["slug"] for item in body["data"]) == ["private", "public"]
    assert body["count"] == 2


def test_public_read_never_widens_into_a_write(client, seeded_blocks) -> None:
    """A public record is readable by a stranger but still not writable.

    The read and write paths use different loaders precisely so this cannot
    drift: widening visibility must not widen ownership.
    """
    public_id = seeded_blocks["public"].id
    response = client.put(
        f"{PREFIX}/prompt-block/edit/{public_id}/",
        headers=_auth("writer"),
        json={"name": "Hijacked", "content": "x", "type": PromptBlockType.TASK.value},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not enough permissions"


# --------------------------------------------------------------------------
# The tier vocabulary itself.
# --------------------------------------------------------------------------


def test_guards_deny_the_tier_below_and_admit_the_tier_at(user_factory) -> None:
    """``require_admin`` has no route today; assert it anyway, so the exported
    tier is proven to behave before the first route relies on it."""
    from fastapi import HTTPException

    for guard, below, at in (
        (require_reader, "user", "reader"),
        (require_writer, "reader", "writer"),
        (require_admin, "writer", "admin"),
    ):
        with pytest.raises(HTTPException) as denied:
            guard(user_factory(below))
        assert denied.value.status_code == 403
        assert guard(user_factory(at)).role.value == at


def test_no_route_carries_a_bare_authenticated_dependency_by_accident() -> None:
    """Every domain router mounts a floor, so a route added later inherits one."""
    from promt_engine_service.app.routes import (
        category,
        dashboard,
        prompt_blocks,
        prompt_templates,
    )

    assert [dep.dependency for dep in category.router.dependencies] == [require_reader]
    assert [dep.dependency for dep in dashboard.router.dependencies] == [require_writer]
    for module in (prompt_blocks, prompt_templates):
        assert len(module.router.dependencies) == 1
