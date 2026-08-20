"""Build-once site for auth and database dependencies.

Import ``auth``, ``engine``, the role-tier guards and ``SessionDep`` from here.
Never call ``build_auth_deps`` or ``create_db_engine`` a second time.

Role tiers
----------
``fastapi-m8`` builds the whole hierarchy inside ``build_auth_deps``; this
module only names the members the service exposes, so a route never has to
reach past ``app/deps.py`` to make an authorization decision. Each guard below
resolves the caller on the SDK's fresh, no-positive-cache user path and denies
with ``403`` through ``has_minimum_role`` — ``is_superuser`` alone never
satisfies a role threshold, so the flag cannot bypass a writer or admin guard.
"""

from typing import Annotated

from fastapi import Depends, HTTPException
from sqlmodel import Session

from fastapi_m8 import (
    AuthDeps,
    DbEngine,
    UserModel,
    build_auth_deps,
    create_db_engine,
)

from .config import settings

# Single instances shared across the entire process.
auth: AuthDeps = build_auth_deps(settings)
engine: DbEngine = create_db_engine(settings)

get_current_user = auth.get_current_user
require_reader = auth.get_current_active_reader
require_writer = auth.get_current_active_writer
require_admin = auth.get_current_active_admin

#: Authenticated floor. Admits every role, ``USER`` included — the tier that may
#: read public items and nothing else. A route carrying this type is stating
#: "any authenticated principal, visibility filtered in the body", which is a
#: decision; a bare re-export of ``auth.CurrentUser`` would state nothing, which
#: is why there is no longer one (F7).
CurrentPrincipal = Annotated[UserModel, Depends(get_current_user)]
CurrentReader = Annotated[UserModel, Depends(require_reader)]
CurrentWriter = Annotated[UserModel, Depends(require_writer)]
CurrentAdmin = Annotated[UserModel, Depends(require_admin)]

get_db = engine.session_dep
SessionDep = Annotated[Session, Depends(get_db)]


def has_reader_privileges(current_user: UserModel) -> bool:
    """Return whether *current_user* meets the ``READER`` threshold.

    Delegates to the SDK-built reader guard rather than re-deriving the role
    hierarchy locally: ``require_reader`` is a plain callable whose only failure
    mode is the ``403`` it raises, so calling it directly is the canonical
    check. ``has_minimum_role``/``RoleType`` (both re-exported by ``fastapi_m8``
    as of A18) are the obvious alternative, but ``require_reader`` already
    encodes the same threshold, so calling it directly avoids a second
    equivalent check.
    """
    try:
        require_reader(current_user)
    except HTTPException:
        return False
    return True
