"""
DashBoard routes
"""

from fastapi import APIRouter, Depends
from promt_engine_service.app.deps import CurrentAdmin, SessionDep, require_admin
from fastapi_m8 import BaseController
from promt_engine_service.controllers.dashboard import DashboardController
from promt_engine_service.schemas.dashboard import RangeActivityType, UsersActivity

# Router floor: admin (operator decision D-C2, superseding the A15 writer
# floor). Both routes aggregate activity across users, and the consuming UI
# has always gated the dashboard on an administrative principal — so the
# writer floor admitted a tier no client ever sent and no view was designed
# for. ``CurrentAdmin`` was exported for exactly this; the ``is_superuser``
# branch inside ``DashboardController`` still narrows own-vs-fleet-wide.
router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_admin)],
)
# pylint: disable=broad-exception-caught, unused-argument


@router.get(
    "/users/activity/",
    response_model=UsersActivity,
    responses=BaseController.get_error_responses(),
)
def get_dash_users_stats(
    session: SessionDep, current_user: CurrentAdmin
) -> UsersActivity:
    """Get phpfina files list from source."""
    return DashboardController.get_dash_users_stats(
        session=session, current_user=current_user, time_range=RangeActivityType.MONTH
    )


@router.get(
    "/users/activity/current/",
    response_model=UsersActivity,
    responses=BaseController.get_error_responses(),
)
def get_dash_current_user_stats(
    session: SessionDep, current_user: CurrentAdmin
) -> UsersActivity:
    """Get phpfina files list from source."""
    return DashboardController.get_dash_users_stats(
        session=session,
        current_user=current_user,
        time_range=RangeActivityType.MONTH,
        is_current=True,
    )
