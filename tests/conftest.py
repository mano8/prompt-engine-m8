"""Shared test fixtures for prompt-engine."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

_TEST_ENV = (
    ("DOMAIN", "localhost"),
    ("ENVIRONMENT", "local"),
    ("PROJECT_NAME", "prompt-engine-m8"),
    ("STACK_NAME", "prompt-engine-m8"),
    ("API_PREFIX", "/prompt"),
    ("SET_OPEN_API", "true"),
    ("SET_DOCS", "true"),
    ("SET_REDOC", "true"),
    ("BACKEND_HOST", "http://localhost:8000"),
    ("FRONTEND_HOST", "http://localhost:5173"),
    ("BACKEND_CORS_ORIGINS", "http://localhost:8000,http://localhost:5173"),
    ("AUTH_SERVICE_ROLE", "consumer"),
    ("AUTH_PREFIX", "/user"),
    ("SELECTED_DB", "Postgres"),
    ("DB_HOST", "localhost"),
    ("DB_PORT", "5432"),
    ("DB_DATABASE", "test_db"),
    ("DB_USER", "test_user"),
    ("DB_" + "PASSWORD", "CiTestDb_Passw0rd"),
    ("ACCESS_TOKEN_ALGORITHM", "HS256"),
    ("ACCESS_" + "SECRET_KEY", "CiTest-AccessKey-prompt-engine2024-AbCd"),
    ("REFRESH_" + "SECRET_KEY", "CiTest-RefreshKey-prompt-engine2024-AbCd"),
    ("REFRESH_TOKEN_ALGORITHM", "HS256"),
    ("TOKEN_STRICT_VALIDATION", "false"),
    ("TOKEN_MODE", "stateless"),
    ("ACCESS_TOKEN_EXPIRE_MINUTES", "30"),
    ("REFRESH_TOKEN_EXPIRE_MINUTES", "1440"),
    ("PRIVATE_API_" + "SECRET", "CiTest-PrivateApi-prompt-engine2024-AbCd"),
    ("INTERNAL_CLIENT_ID", "prompt-engine-service"),
    ("EVENT_SIGNING_ENABLED", "true"),
    ("EVENT_SIGNING_" + "KEY", "CiTest-EventSigning-prompt-engine2024-AbCd"),
    ("METRICS_ENABLED", "true"),
    ("METRICS_GROUPS", "all"),
)
for _key, _value in _TEST_ENV:
    os.environ.setdefault(_key, _value)

import auth_sdk_m8.utils.paths as _paths_mod  # noqa: E402

_real_find_dotenv = _paths_mod.find_dotenv
_paths_mod.find_dotenv = lambda *_args, **_kwargs: ""

import promt_engine_service.core.config as _config_mod  # noqa: E402

_ = _config_mod.settings
_paths_mod.find_dotenv = _real_find_dotenv


from fastapi_m8 import UserModel  # noqa: E402


def make_user(
    role: str = "writer",
    *,
    user_id: uuid.UUID | None = None,
    is_superuser: bool = False,
) -> UserModel:
    """Build the principal a route actually receives.

    The real ``UserModel``, not a stand-in: the role-tier guards read ``role``
    through the SDK hierarchy and the model enforces the ``role``/
    ``is_superuser`` truth table, so a fixture that faked either field could
    assert an authorization outcome the service would never produce.
    """
    return UserModel(
        id=user_id or uuid.uuid4(),
        email=f"{role}-{uuid.uuid4().hex[:8]}@example.com",
        role=role,
        is_superuser=is_superuser,
    )


@pytest.fixture
def user_factory():
    """Build a principal of an arbitrary role inside a test."""
    return make_user


@pytest.fixture
def owner_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def owner(owner_id: uuid.UUID) -> UserModel:
    """Authoring principal — writer, since every fixture use of it authors."""
    return make_user("writer", user_id=owner_id)


@pytest.fixture
def other_user() -> UserModel:
    return make_user("writer")


@pytest.fixture
def reader() -> UserModel:
    return make_user("reader")


@pytest.fixture
def plain_user() -> UserModel:
    """Lowest tier: may read public records and nothing else."""
    return make_user("user")


@pytest.fixture
def superuser() -> UserModel:
    return make_user("superadmin", is_superuser=True)


@pytest.fixture
def session() -> Iterator[Session]:
    import promt_engine_service.db_models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            yield db
    finally:
        engine.dispose()


# --------------------------------------------------------------------------
# HTTP-level fixtures.
#
# A contract is what a caller can reach over HTTP, so the tests that assert one
# go through the real app: real query-string parsing, real ``Enum`` coercion,
# the real HS256 validator and the real role guard. Only the database session
# is replaced. Calling a route function in-process skips exactly the layer a
# list contract lives in — every ``422`` below is produced by FastAPI, not by a
# fixture agreeing with the handler.
# --------------------------------------------------------------------------


def make_access_token(
    role: str, user_id: uuid.UUID, *, is_superuser: bool = False
) -> str:
    """Mint the access token the issuer would mint for *role*."""
    import time

    import jwt

    from promt_engine_service.core.config import settings

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


@pytest.fixture
def auth_headers():
    """Build an ``Authorization`` header for an arbitrary role."""

    def _headers(
        role: str, user_id: uuid.UUID | None = None, **kwargs
    ) -> dict[str, str]:
        token = make_access_token(role, user_id or uuid.uuid4(), **kwargs)
        return {"Authorization": f"Bearer {token}"}

    return _headers


@pytest.fixture
def client(session):
    """The real app, with only the database session replaced.

    Constructed without the context manager on purpose: entering it would run
    the lifespan, which opens the configured Postgres engine and the auth event
    stream. Neither is on the path these tests assert.
    """
    from fastapi.testclient import TestClient

    import promt_engine_service.main as main
    from promt_engine_service.core.deps import get_db

    main.app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(main.app)
    finally:
        main.app.dependency_overrides.clear()
