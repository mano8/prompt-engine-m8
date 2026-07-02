"""Prompt schema and controller tests."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from promt_engine_service.controllers.prompts import (
    DYNAMIC_CONTENT_PLACEHOLDER,
    PromptsController,
    PromtsController,
)
from promt_engine_service.core.db_models import UUIDString, prefixed_fk, prefixed_tables
from promt_engine_service.db_models.prompts import (
    PromptBlock,
    PromptTemplate,
    TemplateBlock,
)
from promt_engine_service.schemas.base import (
    CategoryType,
    LLMProviderType,
    PromptBlockType,
)
from promt_engine_service.schemas.prompts import (
    DynamicBlock,
    PromptBlockModel,
    PromptTemplateModel,
)


def test_enum_values_are_stable() -> None:
    assert CategoryType.PROMPT_BLOCK.value == "prompt_block"
    assert PromptBlockType.INSTRUCTION.value == "instruction"
    assert LLMProviderType.OPENAI.value == "openai"


def test_prefixed_model_helpers_and_uuid_type(owner_id: uuid.UUID) -> None:
    assert prefixed_tables("items").endswith("_items")
    assert prefixed_fk("items", "id").endswith("_items.id")
    uuid_type = UUIDString()
    assert uuid_type.process_bind_param(owner_id, None) == str(owner_id)
    assert uuid_type.process_bind_param(None, None) is None
    assert uuid_type.process_result_value(str(owner_id), None) == owner_id
    assert uuid_type.process_result_value(None, None) is None


def test_prompt_payloads_generate_slugs_and_sanitize() -> None:
    block = PromptBlockModel(
        name="My Block",
        description="desc\u200b",
        content="content\u200b",
        type=PromptBlockType.TASK,
        is_dynamic=True,
    )
    template = PromptTemplateModel(name="My Template", description="desc\u200b")
    dynamic = DynamicBlock(id=1, content="answer\u200b")

    assert block.slug == "my-block"
    assert "\u200b" not in block.content
    assert template.slug == "my-template"
    assert "\u200b" not in template.description
    assert dynamic.content == "answer"


def test_prompt_payload_validators_ignore_non_dict() -> None:
    assert PromptBlockModel.generate_slug_and_sanitize("raw") == "raw"
    assert PromptTemplateModel.generate_slug_and_sanitize("raw") == "raw"
    assert DynamicBlock.sanitize_content("raw") == "raw"
    assert PromptBlockModel.generate_slug_and_sanitize({"content": None}) == {
        "content": None
    }
    assert PromptTemplateModel.generate_slug_and_sanitize({"description": None}) == {
        "description": None
    }


def test_create_update_and_lookup_prompt_block(session, owner) -> None:
    item_in = PromptBlockModel(
        name="Block",
        content="content",
        type=PromptBlockType.CONTEXT,
    )

    block = PromptsController.create_prompt_block(
        session=session,
        current_user=owner,
        item_in=item_in,
    )
    updated = PromptsController.update_prompt_block(
        session=session,
        current_user=owner,
        item_id=block.id,
        item_in=PromptBlockModel(
            name="Block 2",
            content="next",
            type=PromptBlockType.ROLE,
        ),
    )

    assert PromtsController is PromptsController
    assert str(block.owner_id) == str(owner.id)
    assert updated.name == "Block 2"
    assert PromptsController.get_block_for_user(session, owner, block.id).id == block.id


def test_prompt_block_lookup_errors(session, owner, other_user) -> None:
    block = PromptBlock(
        name="Private",
        slug="private",
        content="content",
        type=PromptBlockType.TASK,
        owner_id=owner.id,
    )
    session.add(block)
    session.commit()
    session.refresh(block)

    with pytest.raises(HTTPException) as missing:
        PromptsController.get_block_for_user(session, owner, 999)
    with pytest.raises(HTTPException) as forbidden:
        PromptsController.get_block_for_user(session, other_user, block.id)

    assert missing.value.status_code == 404
    assert forbidden.value.status_code == 403


def test_template_serialization_composition_and_reorder(session, owner) -> None:
    static = PromptBlock(
        name="Static",
        slug="static",
        content="A",
        type=PromptBlockType.ROLE,
        owner_id=owner.id,
    )
    dynamic = PromptBlock(
        name="Dynamic",
        slug="dynamic",
        content="ignored",
        type=PromptBlockType.TASK,
        is_dynamic=True,
        owner_id=owner.id,
    )
    tail = PromptBlock(
        name="Tail",
        slug="tail",
        content="C",
        type=PromptBlockType.FORMAT,
        owner_id=owner.id,
    )
    template = PromptTemplate(name="Tpl", slug="tpl", owner_id=owner.id)
    session.add_all([static, dynamic, tail, template])
    session.commit()
    session.refresh(static)
    session.refresh(dynamic)
    session.refresh(tail)
    session.refresh(template)

    first = PromptsController.add_template_block_and_reorder(
        session=session,
        current_user=owner,
        template_id=template.id,
        block_id=static.id,
    )
    second = PromptsController.add_template_block_and_reorder(
        session=session,
        current_user=owner,
        template_id=template.id,
        block_id=dynamic.id,
        position=1,
    )
    third = PromptsController.add_template_block_and_reorder(
        session=session,
        current_user=owner,
        template_id=template.id,
        block_id=tail.id,
        position=3,
    )
    session.refresh(template)

    assert first.position == 2
    assert second.position == 1
    assert third.position == 3
    assert PromptsController.dump_prompt_templates([template])[0]["slug"] == "tpl"
    assert (
        PromptsController.compose_prompt_content(
            template,
            [DynamicBlock(id=dynamic.id, content="B")],
        )
        == "B\n\nA\n\nC"
    )

    moved = PromptsController.update_template_block_position(
        session=session,
        current_user=owner,
        template_id=template.id,
        block_id=static.id,
        new_position=1,
    )
    assert moved.position == 1

    PromptsController.delete_template_block_and_reorder(
        session=session,
        current_user=owner,
        template_id=template.id,
        block_id=dynamic.id,
    )
    session.refresh(template)
    assert [item.position for item in template.blocks] == [1, 2]


def test_dynamic_placeholder_composition_contract(session, owner) -> None:
    static = PromptBlock(
        id=1,
        name="Static",
        slug="static",
        content=f"Static keeps {DYNAMIC_CONTENT_PLACEHOLDER}",
        type=PromptBlockType.ROLE,
        owner_id=owner.id,
    )
    dynamic = PromptBlock(
        id=2,
        name="Dynamic",
        slug="dynamic",
        content=(
            f"Question:\n{DYNAMIC_CONTENT_PLACEHOLDER}\n"
            f"Repeat: {DYNAMIC_CONTENT_PLACEHOLDER}"
        ),
        type=PromptBlockType.TASK,
        is_dynamic=True,
        owner_id=owner.id,
    )
    legacy_dynamic = PromptBlock(
        id=3,
        name="Legacy dynamic",
        slug="legacy-dynamic",
        content="Stored legacy content",
        type=PromptBlockType.CONTEXT,
        is_dynamic=True,
        owner_id=owner.id,
    )
    template = PromptTemplate(
        name="Tpl",
        slug="tpl",
        blocks=[
            TemplateBlock(
                id=1,
                block_id=static.id,
                template_id=1,
                position=1,
                block=static,
            ),
            TemplateBlock(
                id=2,
                block_id=dynamic.id,
                template_id=1,
                position=2,
                block=dynamic,
            ),
            TemplateBlock(
                id=3,
                block_id=legacy_dynamic.id,
                template_id=1,
                position=3,
                block=legacy_dynamic,
            ),
        ],
        owner_id=owner.id,
    )

    assert PromptsController.compose_prompt_content(
        template,
        [
            DynamicBlock(id=dynamic.id, content="Summarize this\u200b"),
            DynamicBlock(id=legacy_dynamic.id, content="Legacy replacement"),
        ],
    ) == (
        f"Static keeps {DYNAMIC_CONTENT_PLACEHOLDER}\n\n"
        "Question:\nSummarize this\nRepeat: Summarize this\n\n"
        "Legacy replacement"
    )


def test_template_controller_error_branches(session, owner) -> None:
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

    PromptsController.add_template_block_and_reorder(
        session=session,
        current_user=owner,
        template_id=template.id,
        block_id=block.id,
    )

    with pytest.raises(HTTPException) as duplicate:
        PromptsController.add_template_block_and_reorder(
            session=session,
            current_user=owner,
            template_id=template.id,
            block_id=block.id,
        )
    with pytest.raises(HTTPException) as missing_position:
        PromptsController.update_template_block_position(
            session=session,
            current_user=owner,
            template_id=template.id,
            block_id=999,
            new_position=1,
        )
    with pytest.raises(HTTPException) as bad_position:
        PromptsController.update_template_block_position(
            session=session,
            current_user=owner,
            template_id=template.id,
            block_id=block.id,
            new_position=5,
        )
    with pytest.raises(HTTPException) as missing_dynamic:
        PromptsController.compose_prompt_content(
            PromptTemplate(
                name="DynamicTpl",
                slug="dynamic-tpl",
                blocks=[
                    TemplateBlock(
                        id=1,
                        block_id=block.id,
                        template_id=template.id,
                        position=1,
                        block=PromptBlock(
                            id=block.id,
                            name="Dyn",
                            slug="dyn",
                            content="x",
                            type=PromptBlockType.TASK,
                            is_dynamic=True,
                            owner_id=owner.id,
                        ),
                    )
                ],
                owner_id=owner.id,
            ),
            None,
        )
    with pytest.raises(HTTPException) as missing_delete:
        PromptsController.delete_template_block_and_reorder(
            session=session,
            current_user=owner,
            template_id=template.id,
            block_id=999,
        )

    assert duplicate.value.status_code == 409
    assert missing_position.value.status_code == 404
    assert bad_position.value.status_code == 400
    assert missing_dynamic.value.status_code == 400
    assert missing_delete.value.status_code == 404


def test_create_update_and_lookup_prompt_template(session, owner) -> None:
    created = PromptsController.create_prompt_template(
        session=session,
        current_user=owner,
        item_in=PromptTemplateModel(name="Template"),
    )
    updated = PromptsController.update_prompt_template(
        session=session,
        current_user=owner,
        item_id=created.id,
        item_in=PromptTemplateModel(name="Template 2"),
    )

    assert updated.slug == "template-2"
    assert (
        PromptsController.get_template_for_user(session, owner, created.id).id
        == created.id
    )


def test_template_lookup_errors(session, owner, other_user) -> None:
    template = PromptTemplate(name="Private", slug="private", owner_id=owner.id)
    session.add(template)
    session.commit()
    session.refresh(template)

    with pytest.raises(HTTPException) as missing:
        PromptsController.get_template_for_user(session, owner, 999)
    with pytest.raises(HTTPException) as forbidden:
        PromptsController.get_template_for_user(session, other_user, template.id)

    assert missing.value.status_code == 404
    assert forbidden.value.status_code == 403
