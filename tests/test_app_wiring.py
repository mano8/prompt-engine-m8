"""Application wiring, events, and model tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import APIRouter

from promt_engine_service.core import events
from promt_engine_service.db_models.categories import CategoryCreate
from promt_engine_service.db_models.ia_providers import LLMProvider, LLMProviderCreate
from promt_engine_service.db_models.prompts import PromptBlockGenerators
from promt_engine_service.schemas.base import (
    CategoryType,
    LLMProviderType,
    PromptBlockType,
)


def test_model_generators_and_secret_repr(owner_id) -> None:
    category = CategoryCreate(name="Category Name", type=CategoryType.PROMPT_BLOCK)
    provider = LLMProviderCreate(
        name="Open AI",
        type=LLMProviderType.OPENAI,
        api_key="secret",
    )
    block_values = PromptBlockGenerators.generate_slug_and_sanitize(
        {
            "name": "Block Name",
            "content": "content\u200b",
            "description": "desc\u200b",
            "type": PromptBlockType.TASK,
        }
    )
    provider_model = LLMProvider(
        name="Provider",
        slug="provider",
        type=LLMProviderType.OPENAI,
        api_key="secret",
        owner_id=owner_id,
    )

    assert category.slug == "category-name"
    assert provider.slug == "open-ai"
    assert block_values["slug"] == "block-name"
    assert block_values["content"] == "content"
    assert PromptBlockGenerators.generate_slug_and_sanitize("raw") == "raw"
    assert PromptBlockGenerators.generate_slug_and_sanitize({"content": None}) == {
        "content": None
    }
    assert CategoryCreate.generate_slug({"type": CategoryType.PROMPT_BLOCK}) == {
        "type": CategoryType.PROMPT_BLOCK
    }
    assert LLMProviderCreate.generate_slug({"type": LLMProviderType.OPENAI}) == {
        "type": LLMProviderType.OPENAI
    }
    assert "secret" not in repr(provider_model)


def test_make_lifespan_extras_returns_none_when_introspection_url_unset() -> None:
    assert (
        events.make_lifespan_extras(
            SimpleNamespace(INTROSPECTION_URL=None), MagicMock()
        )
        is None
    )


@pytest.mark.anyio
async def test_make_lifespan_extras_wires_sdk_dispatch_and_starts_stops_client() -> (
    None
):
    """The stream client is built with the SDK's own dispatch, not a local
    re-implementation: ``on_event`` must be ``auth.handle_auth_event`` and
    ``on_gap`` must delegate to ``auth.flush_cache``."""
    settings = SimpleNamespace(INTROSPECTION_URL="https://auth.local")

    mock_client = MagicMock()
    mock_client.stop = AsyncMock()
    captured: dict = {}

    def fake_build(s, *, on_event, on_gap, **kw):
        assert s.INTROSPECTION_URL == "https://auth.local"
        captured["on_event"] = on_event
        captured["on_gap"] = on_gap
        return mock_client

    auth = MagicMock()
    with patch(
        "promt_engine_service.core.events.build_event_stream_client",
        side_effect=fake_build,
    ):
        extras = events.make_lifespan_extras(settings, auth)
        assert extras is not None
        async with extras(SimpleNamespace()):
            mock_client.start.assert_called_once()

    mock_client.stop.assert_awaited_once()

    # The client must be wired straight to the SDK's own dispatch methods —
    # no locally re-derived handler in between.
    assert captured["on_event"] is auth.handle_auth_event

    await captured["on_gap"]()
    auth.flush_cache.assert_called_once()


def test_metrics_endpoint_registration(monkeypatch) -> None:
    import promt_engine_service.main as main

    router = APIRouter()
    main._register_metrics_endpoint(router, enabled=False)
    assert not router.routes

    monkeypatch.setattr(
        "fastapi_m8.render_metrics",
        lambda: (b"metrics", "text/plain"),
    )
    main._register_metrics_endpoint(router, enabled=True, credential=None)
    assert router.routes
    response = router.routes[-1].endpoint()
    assert response.body == b"metrics"


@pytest.mark.anyio
async def test_check_db_success_and_failure(monkeypatch) -> None:
    import promt_engine_service.main as main

    class GoodSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def exec(self, statement) -> None:
            assert statement is not None

    class BadEngine:
        def session(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(main.engine, "session", lambda: GoodSession())
    ok = await main.check_db()
    assert ok.name == "database"

    monkeypatch.setattr(main, "engine", BadEngine())
    failed = await main.check_db()
    assert failed.name == "database"
    assert failed.error == "db down"


def test_app_router_imports() -> None:
    import promt_engine_service.app.deps as app_deps
    import promt_engine_service.app.main as app_main
    import promt_engine_service.db_models as db_models
    import promt_engine_service.fastapi_pre_start as pre_start
    import promt_engine_service.main as main

    assert app_deps.SessionDep is not None
    assert app_main.api_router.routes
    assert db_models.PromptBlock is not None
    assert main.app is not None
    assert pre_start.MAX_TRIES == 300
