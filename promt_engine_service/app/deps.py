"""Re-export public dependencies consumed by route modules.

The tier vocabulary is fixed here so a route module cannot reach past it and
invent its own authorization decision:

``CurrentPrincipal``
    Authenticated floor. Every role, ``USER`` included; the handler is then
    responsible for narrowing what it returns to public records.
``CurrentReader``
    Owned reads — lists and items the caller owns.
``CurrentWriter``
    Mutations — add, edit and delete of owned records.
``CurrentAdmin``
    Administrative surface. No route carries it today; it is exported so the
    tier exists in one place the day one does, rather than being invented at
    the call site.

There is deliberately no bare ``CurrentUser`` export (A15/F7).
"""

__all__ = [
    "CurrentAdmin",
    "CurrentPrincipal",
    "CurrentReader",
    "CurrentWriter",
    "SessionDep",
    "get_current_user",
    "require_admin",
    "require_reader",
    "require_writer",
]

from promt_engine_service.core.deps import CurrentAdmin as CurrentAdmin
from promt_engine_service.core.deps import CurrentPrincipal as CurrentPrincipal
from promt_engine_service.core.deps import CurrentReader as CurrentReader
from promt_engine_service.core.deps import CurrentWriter as CurrentWriter
from promt_engine_service.core.deps import SessionDep as SessionDep
from promt_engine_service.core.deps import get_current_user as get_current_user
from promt_engine_service.core.deps import require_admin as require_admin
from promt_engine_service.core.deps import require_reader as require_reader
from promt_engine_service.core.deps import require_writer as require_writer
