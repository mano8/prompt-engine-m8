"""Every PostgreSQL session the service opens runs in UTC (workspace finding G23).

sqlmodel binds aware UTC datetimes; PostgreSQL casts them into the existing
``timestamp without time zone`` columns in the session zone, so a non-UTC server
would store every new row shifted. These tests pin the listener that prevents
it: registered on the service engine, issuing ``SET TIME ZONE 'UTC'`` outside a
transaction, and leaving other dialects alone. The live read against a non-UTC
server runs in ``fa-auth-m8``'s database-integration matrix.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, event

from promt_engine_service.core import deps
from promt_engine_service.core.utc_session import (
    UTC_SESSION_SQL,
    pin_utc_session,
    set_session_utc,
)


class _Cursor:
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection

    def execute(self, sql: str) -> None:
        self._connection.executed.append((sql, self._connection.autocommit))

    def close(self) -> None:
        self._connection.closed_cursors += 1


class _Connection:
    def __init__(self) -> None:
        self.autocommit = False
        self.executed: list[tuple[str, bool]] = []
        self.closed_cursors = 0

    def cursor(self) -> _Cursor:
        return _Cursor(self)


def test_the_service_engine_pins_its_sessions_to_utc() -> None:
    engine: Any = deps.engine._engine
    assert engine.dialect.name == "postgresql"
    assert event.contains(engine, "connect", set_session_utc)


def test_the_listener_sets_utc_outside_a_transaction() -> None:
    connection = _Connection()
    set_session_utc(connection, None)
    assert connection.executed == [(UTC_SESSION_SQL, True)]
    assert connection.autocommit is False
    assert connection.closed_cursors == 1
    assert UTC_SESSION_SQL == "SET TIME ZONE 'UTC'"


def test_pinning_is_idempotent() -> None:
    engine = create_engine("postgresql+psycopg2://u:p@localhost/db")
    pin_utc_session(engine)
    pin_utc_session(engine)
    # One removal leaves nothing behind only if one registration was made.
    event.remove(engine, "connect", set_session_utc)
    assert not event.contains(engine, "connect", set_session_utc)


def test_other_dialects_are_left_alone() -> None:
    engine = create_engine("sqlite://")
    assert pin_utc_session(engine) is engine
    assert not event.contains(engine, "connect", set_session_utc)
