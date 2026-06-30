"""Route and dashboard tests."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from promt_engine_service.app.routes import (
    category,
    dashboard,
    prompt_blocks,
    prompt_templates,
)
from promt_engine_service.controllers.dashboard import DashboardController
from promt_engine_service.db_models.categories import (
    Category,
    CategoryCreate,
    CategoryUpdate,
)
from promt_engine_service.db_models.prompts import PromptBlock, PromptTemplate
from promt_engine_service.schemas.base import CategoryType, PromptBlockType
from promt_engine_service.schemas.dashboard import RangeActivityType, UsersActivity
from promt_engine_service.schemas.prompts import (
    DynamicBlock,
    PromptBlockModel,
    PromptTemplateModel,
)


class BrokenSession:
    def exec(self, statement):
        raise RuntimeError("broken exec")

    def get(self, model, item_id):
        raise RuntimeError("broken get")

    def add(self, item) -> None:
        raise RuntimeError("broken add")

    def commit(self) -> None:
        raise RuntimeError("broken commit")

    def refresh(self, item) -> None:
        raise RuntimeError("broken refresh")


def handled_exception(**kwargs):
    return {"handled": type(kwargs["ex"]).__name__}


@pytest.mark.anyio
async def test_category_crud_routes(session, owner, other_user, superuser) -> None:
    item_in = CategoryCreate(name="General", type=CategoryType.PROMPT_BLOCK)
    created = category.create_item(session=session, current_user=owner, item_in=item_in)
    category_id = created.data["id"]

    own_list = await category.read_root(session, owner)
    admin_list = await category.read_root(session, superuser, skip=0, limit=10)
    fetched = category.read_item(session, owner, category_id)
    updated = category.update_item(
        session=session,
        current_user=owner,
        item_id=category_id,
        item_in=CategoryUpdate(name="Renamed", type=CategoryType.PROMPT_TEMPLATE),
    )

    assert own_list.count == 1
    assert admin_list.count == 1
    assert fetched.success is True
    assert updated.data["slug"] == "renamed"

    with pytest.raises(HTTPException) as denied:
        category.read_item(session, other_user, category_id)
    assert denied.value.status_code == 401

    missing = category.read_item(session, owner, 999)
    assert missing.success is False

    deleted = category.delete_item(session, owner, category_id)
    assert deleted.success is True


def test_category_permission_and_missing_errors(session, owner, other_user) -> None:
    item = Category(
        name="Owned", slug="owned", type=CategoryType.PROMPT_BLOCK, owner_id=owner.id
    )
    session.add(item)
    session.commit()
    session.refresh(item)

    with pytest.raises(HTTPException) as update_denied:
        category.update_item(
            session=session,
            current_user=other_user,
            item_id=item.id,
            item_in=CategoryUpdate(name="Other", type=CategoryType.PROMPT_BLOCK),
        )
    with pytest.raises(HTTPException) as delete_denied:
        category.delete_item(session, other_user, item.id)
    with pytest.raises(HTTPException) as update_missing:
        category.update_item(
            session=session,
            current_user=owner,
            item_id=999,
            item_in=CategoryUpdate(name="Other", type=CategoryType.PROMPT_BLOCK),
        )
    with pytest.raises(HTTPException) as delete_missing:
        category.delete_item(session, owner, 999)

    assert update_denied.value.status_code == 400
    assert delete_denied.value.status_code == 400
    assert update_missing.value.status_code == 404
    assert delete_missing.value.status_code == 404


@pytest.mark.anyio
async def test_category_routes_handle_unexpected_errors(monkeypatch, owner) -> None:
    monkeypatch.setattr(category.BaseController, "handle_exception", handled_exception)
    broken = BrokenSession()

    assert (await category.read_root(broken, owner)) == {"handled": "RuntimeError"}
    assert category.read_item(broken, owner, 1) == {"handled": "RuntimeError"}
    assert category.create_item(
        session=broken,
        current_user=owner,
        item_in=CategoryCreate(name="Bad", type=CategoryType.PROMPT_BLOCK),
    ) == {"handled": "RuntimeError"}
    assert category.update_item(
        session=broken,
        current_user=owner,
        item_id=1,
        item_in=CategoryUpdate(name="Bad", type=CategoryType.PROMPT_BLOCK),
    ) == {"handled": "RuntimeError"}
    assert category.delete_item(broken, owner, 1) == {"handled": "RuntimeError"}


def test_prompt_block_routes(session, owner, other_user, superuser) -> None:
    created = prompt_blocks.add_prompt_block(
        session=session,
        current_user=owner,
        item_in=PromptBlockModel(
            name="Block",
            content="content",
            type=PromptBlockType.TASK,
        ),
    )
    block_id = created.data["id"]

    assert prompt_blocks.prompt_block_list(session, owner).count == 1
    assert prompt_blocks.prompt_block_list(session, superuser).count == 1
    assert prompt_blocks.get_prompt_block(session, owner, block_id).success is True
    assert (
        prompt_blocks.get_prompt_block_by_slug(session, owner, "block").success is True
    )
    assert (
        prompt_blocks.get_prompt_block_by_slug(session, superuser, "block").success
        is True
    )
    assert (
        prompt_blocks.get_prompt_block_by_slug(session, owner, "missing").success
        is False
    )

    with pytest.raises(HTTPException):
        prompt_blocks.update_prompt_block(
            session=session,
            current_user=other_user,
            item_id=block_id,
            item_in=PromptBlockModel(
                name="Denied",
                content="next",
                type=PromptBlockType.ROLE,
            ),
        )

    updated = prompt_blocks.update_prompt_block(
        session=session,
        current_user=owner,
        item_id=block_id,
        item_in=PromptBlockModel(
            name="Block 2",
            content="next",
            type=PromptBlockType.ROLE,
        ),
    )
    assert updated.data["slug"] == "block-2"

    with pytest.raises(HTTPException):
        prompt_blocks.get_prompt_block(session, other_user, block_id)
    assert prompt_blocks.delete_prompt_block(session, owner, block_id).success is True


def test_prompt_block_delete_rejects_template_use(session, owner) -> None:
    block = PromptBlock(
        name="Block",
        slug="block",
        content="content",
        type=PromptBlockType.TASK,
        owner_id=owner.id,
    )
    template = PromptTemplate(name="Tpl", slug="tpl", owner_id=owner.id)
    session.add_all([block, template])
    session.commit()
    session.refresh(block)
    session.refresh(template)
    prompt_templates.add_block_to_prompt_template(
        session=session,
        current_user=owner,
        template_id=template.id,
        block_id=block.id,
    )

    with pytest.raises(HTTPException) as exc:
        prompt_blocks.delete_prompt_block(session, owner, block.id)
    assert exc.value.status_code == 409


def test_prompt_block_routes_handle_unexpected_errors(monkeypatch, owner) -> None:
    monkeypatch.setattr(
        prompt_blocks.BaseController, "handle_exception", handled_exception
    )
    broken = BrokenSession()
    item_in = PromptBlockModel(name="Bad", content="content", type=PromptBlockType.TASK)

    assert prompt_blocks.prompt_block_list(broken, owner) == {"handled": "RuntimeError"}
    assert prompt_blocks.get_prompt_block(broken, owner, 1) == {
        "handled": "RuntimeError"
    }
    assert prompt_blocks.get_prompt_block_by_slug(broken, owner, "bad") == {
        "handled": "RuntimeError"
    }
    assert prompt_blocks.add_prompt_block(
        session=broken,
        current_user=owner,
        item_in=item_in,
    ) == {"handled": "RuntimeError"}
    assert prompt_blocks.update_prompt_block(
        session=broken,
        current_user=owner,
        item_id=1,
        item_in=item_in,
    ) == {"handled": "RuntimeError"}
    assert prompt_blocks.delete_prompt_block(broken, owner, 1) == {
        "handled": "RuntimeError"
    }


def test_prompt_template_routes(session, owner, superuser) -> None:
    block = PromptBlock(
        name="Dynamic",
        slug="dynamic",
        content="ignored",
        type=PromptBlockType.TASK,
        is_dynamic=True,
        owner_id=owner.id,
    )
    session.add(block)
    session.commit()
    session.refresh(block)

    created = prompt_templates.add_prompt_template(
        session=session,
        current_user=owner,
        item_in=PromptTemplateModel(name="Tpl"),
    )
    template_id = created.data["id"]

    assert prompt_templates.prompt_template_list(session, owner).count == 1
    assert prompt_templates.prompt_template_list(session, superuser).count == 1
    assert (
        prompt_templates.get_prompt_template(session, owner, template_id).success
        is True
    )
    assert (
        prompt_templates.get_prompt_template_by_slug(session, owner, "tpl").success
        is True
    )
    assert (
        prompt_templates.get_prompt_template_by_slug(session, superuser, "tpl").success
        is True
    )
    assert (
        prompt_templates.get_prompt_template_by_slug(session, owner, "missing").success
        is False
    )
    assert (
        prompt_templates.get_prompt_template_blocks(session, owner, template_id).success
        is False
    )

    linked = prompt_templates.add_block_to_prompt_template(
        session=session,
        current_user=owner,
        template_id=template_id,
        block_id=block.id,
    )
    assert linked.success is True
    assert (
        prompt_templates.get_prompt_template_blocks(session, owner, template_id).success
        is True
    )

    composed = prompt_templates.compose_prompt_template(
        session,
        owner,
        template_id,
        [DynamicBlock(id=block.id, content="answer")],
    )
    assert composed.data == {"content": "answer"}

    moved = prompt_templates.update_prompt_template_block_position(
        session=session,
        current_user=owner,
        template_id=template_id,
        block_id=block.id,
        position=1,
    )
    assert moved.success is True
    removed = prompt_templates.delete_block_from_prompt_template(
        session=session,
        current_user=owner,
        template_id=template_id,
        block_id=block.id,
    )
    assert removed.success is True

    prompt_templates.add_block_to_prompt_template(
        session=session,
        current_user=owner,
        template_id=template_id,
        block_id=block.id,
    )

    updated = prompt_templates.update_prompt_template(
        session=session,
        current_user=owner,
        item_id=template_id,
        item_in=PromptTemplateModel(name="Tpl 2"),
    )
    assert updated.data["slug"] == "tpl-2"
    assert (
        prompt_templates.delete_prompt_template(session, owner, template_id).success
        is True
    )


def test_prompt_template_route_http_errors_raise(session, owner, other_user) -> None:
    template = PromptTemplate(name="Private", slug="private", owner_id=owner.id)
    session.add(template)
    session.commit()
    session.refresh(template)

    calls = [
        lambda: prompt_templates.get_prompt_template(session, other_user, template.id),
        lambda: prompt_templates.get_prompt_template_blocks(
            session, other_user, template.id
        ),
        lambda: prompt_templates.compose_prompt_template(
            session, other_user, template.id
        ),
        lambda: prompt_templates.update_prompt_template(
            session=session,
            current_user=other_user,
            item_id=template.id,
            item_in=PromptTemplateModel(name="Denied"),
        ),
        lambda: prompt_templates.delete_prompt_template(
            session, other_user, template.id
        ),
        lambda: prompt_templates.add_block_to_prompt_template(
            session=session,
            current_user=other_user,
            template_id=template.id,
            block_id=999,
        ),
        lambda: prompt_templates.update_prompt_template_block_position(
            session=session,
            current_user=other_user,
            template_id=template.id,
            block_id=999,
        ),
        lambda: prompt_templates.delete_block_from_prompt_template(
            session=session,
            current_user=other_user,
            template_id=template.id,
            block_id=999,
        ),
    ]

    for call in calls:
        with pytest.raises(HTTPException):
            call()


def test_prompt_template_routes_handle_unexpected_errors(monkeypatch, owner) -> None:
    monkeypatch.setattr(
        prompt_templates.BaseController,
        "handle_exception",
        handled_exception,
    )
    broken = BrokenSession()
    item_in = PromptTemplateModel(name="Bad")

    assert prompt_templates.prompt_template_list(broken, owner) == {
        "handled": "RuntimeError"
    }
    assert prompt_templates.get_prompt_template(broken, owner, 1) == {
        "handled": "RuntimeError"
    }
    assert prompt_templates.get_prompt_template_by_slug(broken, owner, "bad") == {
        "handled": "RuntimeError"
    }
    assert prompt_templates.get_prompt_template_blocks(broken, owner, 1) == {
        "handled": "RuntimeError"
    }
    assert prompt_templates.compose_prompt_template(broken, owner, 1) == {
        "handled": "RuntimeError"
    }
    assert prompt_templates.add_prompt_template(
        session=broken,
        current_user=owner,
        item_in=item_in,
    ) == {"handled": "RuntimeError"}
    assert prompt_templates.update_prompt_template(
        session=broken,
        current_user=owner,
        item_id=1,
        item_in=item_in,
    ) == {"handled": "RuntimeError"}
    assert prompt_templates.delete_prompt_template(broken, owner, 1) == {
        "handled": "RuntimeError"
    }
    assert prompt_templates.add_block_to_prompt_template(
        session=broken,
        current_user=owner,
        block_id=1,
        template_id=1,
    ) == {"handled": "RuntimeError"}
    assert prompt_templates.update_prompt_template_block_position(
        session=broken,
        current_user=owner,
        block_id=1,
        template_id=1,
    ) == {"handled": "RuntimeError"}
    assert prompt_templates.delete_block_from_prompt_template(
        session=broken,
        current_user=owner,
        block_id=1,
        template_id=1,
    ) == {"handled": "RuntimeError"}


def test_dashboard_range_activity_and_stats(session, owner, superuser) -> None:
    for time_range in RangeActivityType:
        start, end = DashboardController.get_range_activity(time_range)
        assert start < end
    with pytest.raises(ValueError):
        DashboardController.get_range_activity("invalid")

    session.add(
        Category(
            name="Owned",
            slug="owned",
            type=CategoryType.PROMPT_BLOCK,
            owner_id=owner.id,
        )
    )
    session.commit()

    own = DashboardController.get_dash_users_stats(
        session, owner, RangeActivityType.MONTH
    )
    admin = DashboardController.get_dash_users_stats(
        session, superuser, RangeActivityType.MONTH
    )
    current = DashboardController.get_dash_users_stats(
        session,
        superuser,
        RangeActivityType.MONTH,
        is_current=True,
    )
    assert isinstance(own, UsersActivity)
    assert admin.activity["max"] >= 1
    assert own.activity["max"] >= 1
    assert current.nb_users == 0
    assert dashboard.get_dash_users_stats(session, owner).activity["max"] >= 1
    assert dashboard.get_dash_current_user_stats(session, owner).nb_users == 0


def test_dashboard_december_and_exception(monkeypatch, session, owner) -> None:
    class FixedDateTime:
        @classmethod
        def now(cls):
            from datetime import datetime

            return datetime(2026, 12, 15, 10, 30)

    monkeypatch.setattr(
        "promt_engine_service.controllers.dashboard.datetime",
        FixedDateTime,
    )
    start, end = DashboardController.get_range_activity(RangeActivityType.MONTH)
    assert start.month == 12
    assert end.year == 2027
    assert end.month == 1

    monkeypatch.setattr(
        DashboardController,
        "get_activity_count_by_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("bad stats")),
    )
    monkeypatch.setattr(
        "promt_engine_service.controllers.dashboard.BaseController.handle_exception",
        handled_exception,
    )
    assert DashboardController.get_dash_users_stats(
        session,
        owner,
        RangeActivityType.MONTH,
    ) == {"handled": "RuntimeError"}
