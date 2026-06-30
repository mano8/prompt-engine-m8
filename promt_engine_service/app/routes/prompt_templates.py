"""Prompt template routes."""

from typing import Any, Optional, Union, cast

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import selectinload
from sqlmodel import func, select

from auth_sdk_m8.controllers.base import BaseController
from auth_sdk_m8.schemas.base import ResponseMessage, ResponseModelBase
from promt_engine_service.app.deps import CurrentUser, SessionDep
from promt_engine_service.controllers.prompts import PromptsController
from promt_engine_service.db_models.prompts import PromptTemplate, TemplateBlock
from promt_engine_service.schemas.prompts import (
    DynamicBlock,
    PromptTemplateModel,
    PromptTemplatesList,
)

router = APIRouter(prefix="/prompt-template", tags=["prompt-template"])
# pylint: disable=not-callable,broad-exception-caught


@router.get(
    "/",
    response_model=PromptTemplatesList,
    responses=BaseController.get_error_responses(),
)
def prompt_template_list(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """Retrieve prompt templates visible to the current user."""
    try:
        statement = (
            select(PromptTemplate)
            .options(
                selectinload(cast(Any, PromptTemplate.blocks)).selectinload(
                    cast(Any, TemplateBlock.block)
                )
            )
            .offset(skip)
            .limit(limit)
        )
        count_statement = select(func.count()).select_from(PromptTemplate)
        if not current_user.is_superuser:
            statement = statement.where(PromptTemplate.owner_id == current_user.id)
            count_statement = count_statement.where(
                PromptTemplate.owner_id == current_user.id
            )
        items = session.exec(statement).all()
        return PromptTemplatesList(
            count=session.exec(count_statement).one(),
            data=PromptsController.dump_prompt_templates(items),
        )
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.get(
    "/get/{item_id}/",
    response_model=Union[ResponseModelBase, ResponseMessage],
    responses=BaseController.get_error_responses(),
)
def get_prompt_template(
    session: SessionDep, current_user: CurrentUser, item_id: int
) -> Any:
    """Get a prompt template by ID."""
    try:
        template = PromptsController.get_template_for_user(
            session, current_user, item_id
        )
        return ResponseModelBase(
            success=True, data=PromptsController.dump_prompt_template(template)
        )
    except HTTPException:
        raise
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.get(
    "/get_by_slug/{item_slug}/",
    response_model=Union[ResponseModelBase, ResponseMessage],
    responses=BaseController.get_error_responses(),
)
def get_prompt_template_by_slug(
    session: SessionDep,
    current_user: CurrentUser,
    item_slug: str,
) -> Any:
    """Get a prompt template by slug."""
    try:
        statement = (
            select(PromptTemplate)
            .where(PromptTemplate.slug == item_slug)
            .options(
                selectinload(cast(Any, PromptTemplate.blocks)).selectinload(
                    cast(Any, TemplateBlock.block)
                )
            )
        )
        if not current_user.is_superuser:
            statement = statement.where(PromptTemplate.owner_id == current_user.id)
        template = session.exec(statement).first()
        if template is None:
            return ResponseMessage(success=False, msg="Item not found.")
        return ResponseModelBase(
            success=True, data=PromptsController.dump_prompt_template(template)
        )
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.get(
    "/get-blocks/{item_id}/",
    response_model=Union[ResponseModelBase, ResponseMessage],
    responses=BaseController.get_error_responses(),
)
def get_prompt_template_blocks(
    session: SessionDep, current_user: CurrentUser, item_id: int
) -> Any:
    """Get ordered blocks for a prompt template."""
    try:
        template = PromptsController.get_template_for_user(
            session, current_user, item_id
        )
        if not template.blocks:
            return ResponseMessage(success=False, msg="Empty template blocks!")
        return ResponseModelBase(
            success=True, data=PromptsController.dump_template_blocks(template.blocks)
        )
    except HTTPException:
        raise
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.post(
    "/compose/{item_id}/",
    response_model=Union[ResponseModelBase, ResponseMessage],
    responses=BaseController.get_error_responses(),
)
def compose_prompt_template(
    session: SessionDep,
    current_user: CurrentUser,
    item_id: int,
    dynamic_content: Optional[list[DynamicBlock]] = None,
) -> Any:
    """Compose a prompt template into a deterministic prompt string."""
    try:
        template = PromptsController.get_template_for_user(
            session, current_user, item_id
        )
        content = PromptsController.compose_prompt_content(
            template=template,
            dynamic_content=dynamic_content,
        )
        return ResponseModelBase(success=True, data={"content": content})
    except HTTPException:
        raise
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.post(
    "/add/",
    response_model=ResponseModelBase,
    responses=BaseController.get_error_responses(),
)
def add_prompt_template(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    item_in: PromptTemplateModel,
) -> Any:
    """Create a prompt template."""
    try:
        template = PromptsController.create_prompt_template(
            session=session,
            current_user=current_user,
            item_in=item_in,
        )
        return ResponseModelBase(success=True, data=template.model_dump())
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.put(
    "/edit/{item_id}/",
    response_model=ResponseModelBase,
    responses=BaseController.get_error_responses(),
)
def update_prompt_template(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    item_id: int,
    item_in: PromptTemplateModel,
) -> Any:
    """Update a prompt template."""
    try:
        template = PromptsController.update_prompt_template(
            session=session,
            current_user=current_user,
            item_id=item_id,
            item_in=item_in,
        )
        return ResponseModelBase(success=True, data=template.model_dump())
    except HTTPException:
        raise
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.delete(
    "/delete/{item_id}/",
    response_model=ResponseMessage,
    responses=BaseController.get_error_responses(),
)
def delete_prompt_template(
    session: SessionDep, current_user: CurrentUser, item_id: int
) -> ResponseMessage:
    """Delete a prompt template."""
    try:
        template = PromptsController.get_template_for_user(
            session, current_user, item_id
        )
        for template_block in list(template.blocks):
            session.delete(template_block)
        session.flush()
        session.delete(template)
        session.commit()
        return ResponseMessage(success=True, msg="Prompt template deleted successfully")
    except HTTPException:
        raise
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.get(
    "/{template_id}/add-block/{block_id}/",
    response_model=ResponseModelBase,
    responses=BaseController.get_error_responses(),
)
def add_block_to_prompt_template(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    block_id: int,
    template_id: int,
    position: int = 0,
) -> Any:
    """Attach a block to a prompt template."""
    try:
        template_block = PromptsController.add_template_block_and_reorder(
            session=session,
            current_user=current_user,
            template_id=template_id,
            block_id=block_id,
            position=position,
        )
        return ResponseModelBase(success=True, data=template_block.model_dump())
    except HTTPException:
        raise
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.get(
    "/{template_id}/set-block-position/{block_id}/",
    response_model=ResponseModelBase,
    responses=BaseController.get_error_responses(),
)
def update_prompt_template_block_position(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    block_id: int,
    template_id: int,
    position: int = 1,
) -> Any:
    """Update a block position in a prompt template."""
    try:
        template_block = PromptsController.update_template_block_position(
            session=session,
            current_user=current_user,
            template_id=template_id,
            block_id=block_id,
            new_position=position,
        )
        return ResponseModelBase(success=True, data=template_block.model_dump())
    except HTTPException:
        raise
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.delete(
    "/{template_id}/delete-block/{block_id}/",
    response_model=ResponseMessage,
    responses=BaseController.get_error_responses(),
)
def delete_block_from_prompt_template(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    block_id: int,
    template_id: int,
) -> Any:
    """Remove a block from a prompt template."""
    try:
        PromptsController.delete_template_block_and_reorder(
            session=session,
            current_user=current_user,
            template_id=template_id,
            block_id=block_id,
        )
        return ResponseMessage(success=True, msg="Block removed successfully.")
    except HTTPException:
        raise
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)
