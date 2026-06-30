"""Shared test fixtures for prompt-engine."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


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
