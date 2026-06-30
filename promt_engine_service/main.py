"""promt_engine_service entry point.

All CORS, health, lifespan, and shared metrics middleware/collectors are wired
by ``create_app``. Only prompt-engine routes and the optional guarded
``/metrics`` endpoint live here.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlmodel import select

from auth_sdk_m8.security.guards import make_scrape_credential_guard
from fastapi_m8 import (
    AppLifecycle,
    HealthCheckResult,
    HealthConfig,
    HealthStatus,
    create_app,
)

from promt_engine_service.app.main import api_router as domain_router
from promt_engine_service.core.config import settings
from promt_engine_service.core.deps import auth, engine
from promt_engine_service.core.events import make_lifespan_extras


async def check_db() -> HealthCheckResult:
    """Check database reachability."""
    try:
        with engine.session() as session:
            session.exec(select(1))
        return HealthCheckResult.from_bool("database", True)
    except Exception as exc:
        return HealthCheckResult(
            name="database",
            status=HealthStatus.FAIL,
            error=str(exc),
        )


def _register_metrics_endpoint(
    router: APIRouter,
    *,
    enabled: bool,
    credential: str | None = None,
) -> None:
    """Expose Prometheus metrics when enabled.

    When ``credential`` is set, callers must present
    ``Authorization: Bearer <credential>``. When unset, the network boundary is
    the control, matching the full-consumer pattern used by media-service-m8.
    """
    if not enabled:
        return

    from auth_sdk_m8.observability.metrics import render as _render_metrics  # noqa: PLC0415

    guard = make_scrape_credential_guard(credential)

    @router.get("/metrics", include_in_schema=False, dependencies=[Depends(guard)])
    def metrics_endpoint() -> Response:
        data, content_type = _render_metrics()
        return Response(content=data, media_type=content_type)


api_router = APIRouter(prefix=settings.API_PREFIX)
api_router.include_router(domain_router)
_credential = settings.METRICS_SCRAPE_CREDENTIAL
_register_metrics_endpoint(
    api_router,
    enabled=settings.METRICS_ENABLED,
    credential=_credential.get_secret_value() if _credential else None,
)

app = create_app(
    settings,
    api_router,
    service_name="prompt-engine-m8",
    service_version=settings.SERVICE_VERSION,
    health=HealthConfig(checks=[check_db]),
    lifecycle=AppLifecycle(
        auth_deps=auth,
        db_engine=engine,
        lifespan_extras=make_lifespan_extras(settings, auth),
    ),
)