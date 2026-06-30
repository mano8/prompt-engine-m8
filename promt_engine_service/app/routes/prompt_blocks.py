"""Prompt block routes."""

from typing import Any, Union

from fastapi import APIRouter, HTTPException
from sqlmodel import func, select

from auth_sdk_m8.controllers.base import BaseController
from auth_sdk_m8.schemas.base import ResponseMessage, ResponseModelBase
from promt_engine_service.app.deps import CurrentUser, SessionDep
from promt_engine_service.controllers.prompts import PromptsController
from promt_engine_service.db_models.prompts import PromptBlock, PromptBlocksPublic
from promt_engine_service.schemas.prompts import PromptBlockModel

router = APIRouter(prefix="/prompt-block", tags=["prompt-block"])
# pylint: disable=not-callable,broad-exception-caught


@router.get(
    "/",
    response_model=PromptBlocksPublic,
    responses=BaseController.get_error_responses(),
)
def prompt_block_list(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """Retrieve prompt blocks visible to the current user."""
    try:
        statement = select(PromptBlock).offset(skip).limit(limit)
        count_statement = select(func.count()).select_from(PromptBlock)
        if not current_user.is_superuser:
            statement = statement.where(PromptBlock.owner_id == current_user.id)
            count_statement = count_statement.where(PromptBlock.owner_id == current_user.id)
        return PromptBlocksPublic(
            data=session.exec(statement).all(),
            count=session.exec(count_statement).one(),
        )
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.get(
    "/get/{item_id}/",
    response_model=Union[ResponseModelBase, ResponseMessage],
    responses=BaseController.get_error_responses(),
)
def get_prompt_block(session: SessionDep, current_user: CurrentUser, item_id: int) -> Any:
    """Get a prompt block by ID."""
    try:
        block = PromptsController.get_block_for_user(session, current_user, item_id)
        return ResponseModelBase(success=True, data=block.model_dump())
    except HTTPException:
        raise
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.get(
    "/get_by_slug/{item_slug}/",
    response_model=Union[ResponseModelBase, ResponseMessage],
    responses=BaseController.get_error_responses(),
)
def get_prompt_block_by_slug(
    session: SessionDep,
    current_user: CurrentUser,
    item_slug: str,
) -> Any:
    """Get a prompt block by slug."""
    try:
        statement = select(PromptBlock).where(PromptBlock.slug == item_slug)
        if not current_user.is_superuser:
            statement = statement.where(PromptBlock.owner_id == current_user.id)
        block = session.exec(statement).first()
        if block is None:
            return ResponseMessage(success=False, msg="Item not found.")
        return ResponseModelBase(success=True, data=block.model_dump())
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.post(
    "/add/",
    response_model=ResponseModelBase,
    responses=BaseController.get_error_responses(),
)
def add_prompt_block(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    item_in: PromptBlockModel,
) -> Any:
    """Create a prompt block."""
    try:
        block = PromptsController.create_prompt_block(
            session=session,
            current_user=current_user,
            item_in=item_in,
        )
        return ResponseModelBase(success=True, data=block.model_dump())
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.put(
    "/edit/{item_id}/",
    response_model=ResponseModelBase,
    responses=BaseController.get_error_responses(),
)
def update_prompt_block(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    item_id: int,
    item_in: PromptBlockModel,
) -> Any:
    """Update a prompt block."""
    try:
        block = PromptsController.update_prompt_block(
            session=session,
            current_user=current_user,
            item_id=item_id,
            item_in=item_in,
        )
        return ResponseModelBase(success=True, data=block.model_dump())
    except HTTPException:
        raise
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.delete(
    "/delete/{item_id}/",
    response_model=ResponseMessage,
    responses=BaseController.get_error_responses(),
)
def delete_prompt_block(
    session: SessionDep,
    current_user: CurrentUser,
    item_id: int,
) -> ResponseMessage:
    """Delete a prompt block."""
    try:
        block = PromptsController.get_block_for_user(session, current_user, item_id)
        if block.templates:
            raise HTTPException(status_code=409, detail="Prompt block is used by a template")
        session.delete(block)
        session.commit()
        return ResponseMessage(success=True, msg="Prompt block deleted successfully")
    except HTTPException:
        raise
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)