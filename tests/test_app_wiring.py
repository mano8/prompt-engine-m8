"""Application wiring, events, and model tests."""

from __future__ import annotations

from types import SimpleNamespace

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


class AuthRecorder:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, str | None]] = []

    def evict_jti(self, jti: str) -> None:
        self.calls.append(("jti", jti))
        if self.fail:
            raise RuntimeError("boom")

    def evict_user(self, user_id: str) -> None:
        self.calls.append(("user", user_id))
        if self.fail:
            raise RuntimeError("boom")

    def flush_cache(self) -> None:
        self.calls.append(("flush", None))
        if self.fail:
            raise RuntimeError("boom")


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


@pytest.mark.anyio
async def test_handle_auth_event_dispatches_and_logs() -> None:
    auth = AuthRecorder()

    await events.handle_auth_event(
        SimpleNamespace(payload={"event_type": "session.revoked", "jti": "j1"}),
        auth=auth,
    )
    await events.handle_auth_event(
        SimpleNamespace(payload={"event_type": "session.revoked", "user_id": "u1"}),
        auth=auth,
    )
    await events.handle_auth_event(
        SimpleNamespace(payload={"event_type": "user.deleted", "user_id": "u2"}),
        auth=auth,
    )
    await events.handle_auth_event(
        SimpleNamespace(payload={"event_type": "unknown"}), auth=auth
    )

    assert auth.calls == [("jti", "j1"), ("user", "u1"), ("user", "u2")]

    await events.handle_auth_event(
        SimpleNamespace(payload={"event_type": "session.revoked", "jti": "bad"}),
        auth=AuthRecorder(fail=True),
    )


@pytest.mark.anyio
async def test_handle_auth_gap_and_lifespan(monkeypatch) -> None:
    auth = AuthRecorder()
    await events.handle_auth_gap(auth=auth)
    assert auth.calls == [("flush", None)]
    await events.handle_auth_gap(auth=AuthRecorder(fail=True))

    class Client:
        def __init__(self) -> None:
            self.started = False
            self.stopped = False

        def start(self) -> None:
            self.started = True

        async def stop(self) -> None:
            self.stopped = True

    client = Client()

    callbacks = {}

    def fake_client(settings, *, on_event, on_gap):
        assert settings.INTROSPECTION_URL == "https://auth.local"
        callbacks["on_event"] = on_event
        callbacks["on_gap"] = on_gap
        return client

    monkeypatch.setattr(events, "build_event_stream_client", fake_client)
    settings = SimpleNamespace(INTROSPECTION_URL="https://auth.local")
    async with events._stream_lifespan(settings, auth):
        assert client.started is True
        await callbacks["on_event"](
            SimpleNamespace(payload={"event_type": "user.deleted", "user_id": "u3"})
        )
        await callbacks["on_gap"]()
    assert client.stopped is True
    assert ("user", "u3") in auth.calls
    assert ("flush", None) in auth.calls

    assert (
        events.make_lifespan_extras(SimpleNamespace(INTROSPECTION_URL=None), auth)
        is None
    )
    extras = events.make_lifespan_extras(settings, auth)
    async with extras(SimpleNamespace()):
        assert client.started is True


def test_metrics_endpoint_registration(monkeypatch) -> None:
    import promt_engine_service.main as main

    router = APIRouter()
    main._register_metrics_endpoint(router, enabled=False)
    assert not router.routes

    monkeypatch.setattr(
        "auth_sdk_m8.observability.metrics.render",
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
