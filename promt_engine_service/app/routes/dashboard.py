"""
DashBoard routes
"""

from fastapi import APIRouter, Depends
from promt_engine_service.app.deps import CurrentWriter, SessionDep, require_writer
from auth_sdk_m8.controllers.base import BaseController
from promt_engine_service.controllers.dashboard import DashboardController
from promt_engine_service.schemas.dashboard import RangeActivityType, UsersActivity

# Router floor: writer (operator decision, A15). Both routes report activity
# counts over authored content; a reader that cannot author has nothing to see
# here, and the fleet-wide view is separately gated by the ``is_superuser``
# branch inside ``DashboardController``.
router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_writer)],
)
# pylint: disable=broad-exception-caught, unused-argument


@router.get(
    "/users/activity/",
    response_model=UsersActivity,
    responses=BaseController.get_error_responses(),
)
def get_dash_users_stats(
    session: SessionDep, current_user: CurrentWriter
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
    session: SessionDep, current_user: CurrentWriter
) -> UsersActivity:
    """Get phpfina files list from source."""
    return DashboardController.get_dash_users_stats(
        session=session,
        current_user=current_user,
        time_range=RangeActivityType.MONTH,
        is_current=True,
    )
