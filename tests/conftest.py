"""Shared test fixtures for prompt-engine."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

_TEST_ENV = {
    "DOMAIN": "localhost",
    "ENVIRONMENT": "local",
    "PROJECT_NAME": "prompt-engine-m8",
    "STACK_NAME": "prompt-engine-m8",
    "API_PREFIX": "/prompt",
    "SET_OPEN_API": "true",
    "SET_DOCS": "true",
    "SET_REDOC": "true",
    "BACKEND_HOST": "http://localhost:8000",
    "FRONTEND_HOST": "http://localhost:5173",
    "BACKEND_CORS_ORIGINS": "http://localhost:8000,http://localhost:5173",
    "AUTH_SERVICE_ROLE": "consumer",
    "AUTH_PREFIX": "/user",
    "SELECTED_DB": "Postgres",
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
    "DB_DATABASE": "test_db",
    "DB_USER": "test_user",
    "DB_PASSWORD": "CiTestDb_Passw0rd",
    "ACCESS_TOKEN_ALGORITHM": "HS256",
    "ACCESS_SECRET_KEY": "CiTest-AccessKey-prompt-engine2024-AbCd",
    "REFRESH_SECRET_KEY": "CiTest-RefreshKey-prompt-engine2024-AbCd",
    "REFRESH_TOKEN_ALGORITHM": "HS256",
    "TOKEN_STRICT_VALIDATION": "false",
    "TOKEN_MODE": "stateless",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
    "REFRESH_TOKEN_EXPIRE_MINUTES": "1440",
    "PRIVATE_API_SECRET": "CiTest-PrivateApi-prompt-engine2024-AbCd",
    "INTERNAL_CLIENT_ID": "prompt-engine-service",
    "EVENT_SIGNING_ENABLED": "true",
    "EVENT_SIGNING_KEY": "CiTest-EventSigning-prompt-engine2024-AbCd",
    "METRICS_ENABLED": "true",
    "METRICS_GROUPS": "all",
}
for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)

import auth_sdk_m8.utils.paths as _paths_mod  # noqa: E402

_real_find_dotenv = _paths_mod.find_dotenv
_paths_mod.find_dotenv = lambda *_args, **_kwargs: ""

import promt_engine_service.core.config as _config_mod  # noqa: E402

_ = _config_mod.settings
_paths_mod.find_dotenv = _real_find_dotenv


@dataclass
class User:
    """Minimal authenticated user shape used by route/controller tests."""

    id: uuid.UUID
    is_superuser: bool = False


@pytest.fixture
def owner_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def owner(owner_id: uuid.UUID) -> User:
    return User(id=owner_id)


@pytest.fixture
def other_user() -> User:
    return User(id=uuid.uuid4())


@pytest.fixture
def superuser() -> User:
    return User(id=uuid.uuid4(), is_superuser=True)


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
