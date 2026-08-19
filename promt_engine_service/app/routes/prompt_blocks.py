"""Prompt block routes."""

from typing import Annotated, Any, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import func, select

from fastapi_m8 import BaseController, ResponseMessage, ResponseModelBase
from promt_engine_service.app.deps import (
    CurrentPrincipal,
    CurrentWriter,
    SessionDep,
    get_current_user,
)
from promt_engine_service.controllers.prompts import (
    ListQueryController,
    PromptsController,
)
from promt_engine_service.db_models.prompts import PromptBlock, PromptBlocksPublic
from promt_engine_service.schemas.list_params import (
    PROMPT_BLOCK_LIST_VOCABULARY,
    MAX_SEARCH_LENGTH,
    PromptBlockSearchParam,
    PromptBlockSortParam,
    SortOrderParam,
)
from promt_engine_service.schemas.prompts import PromptBlockModel

# Router floor: authentication. The read routes below deliberately admit the
# ``USER`` tier (public blocks only), so a reader floor would be wrong here —
# but a route added later must not be reachable anonymously, and mounting the
# floor is what makes that inherited rather than remembered.
router = APIRouter(
    prefix="/prompt-block",
    tags=["prompt-block"],
    dependencies=[Depends(get_current_user)],
)
# pylint: disable=not-callable,broad-exception-caught


@router.get(
    "/",
    response_model=PromptBlocksPublic,
    responses=BaseController.get_error_responses(),
)
def prompt_block_list(
    session: SessionDep,
    current_user: CurrentPrincipal,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1)] = 100,
    q: Annotated[str, Query(max_length=MAX_SEARCH_LENGTH)] = "",
    csrc: PromptBlockSearchParam = None,
    sort: PromptBlockSortParam = None,
    order: SortOrderParam = None,
    f: Annotated[
        str,
        Query(
            max_length=MAX_SEARCH_LENGTH,
            description=(
                "Comma-joined facet values, combined with OR. Allowed: "
                + ", ".join(PROMPT_BLOCK_LIST_VOCABULARY.facets)
                + "."
            ),
        ),
    ] = "",
) -> Any:
    """Retrieve prompt blocks visible to the current user.

    ``q`` searches every declared block column, or only ``csrc`` when one is
    named; ``f`` carries comma-joined facet values combined with ``OR``;
    ``sort``/``order`` order the page. Every value is allow-listed by
    ``ListQueryController`` — an undeclared one is a ``422``.

    ``count`` is the count of the **filtered** set, not of everything visible.
    That is the point of the parameters: a paginator driven by an unfiltered
    count reports pages that do not exist. With none of the new parameters
    present the response is byte-for-byte what ``skip``/``limit`` always
    returned, ordering included — an absent ``sort`` adds no ``ORDER BY``.
    """
    try:
        statement = select(PromptBlock)
        count_statement = select(func.count()).select_from(PromptBlock)
        predicates = ListQueryController.prompt_block_predicates(q=q, csrc=csrc, f=f)
        visibility = PromptsController.visibility_filter(PromptBlock, current_user)
        if visibility is not None:
            predicates.append(visibility)
        for predicate in predicates:
            statement = statement.where(predicate)
            count_statement = count_statement.where(predicate)
        if sort is not None:
            statement = statement.order_by(
                ListQueryController.order_clause(
                    ListQueryController.BLOCK_SORT_COLUMNS, sort, order
                )
            )
        statement = statement.offset(skip).limit(limit)
        return PromptBlocksPublic(
            data=session.exec(statement).all(),
            count=session.exec(count_statement).one(),
        )
    except HTTPException:
        raise
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.get(
    "/get/{item_id}/",
    response_model=Union[ResponseModelBase, ResponseMessage],
    responses=BaseController.get_error_responses(),
)
def get_prompt_block(
    session: SessionDep, current_user: CurrentPrincipal, item_id: int
) -> Any:
    """Get a prompt block by ID."""
    try:
        block = PromptsController.get_readable_block(session, current_user, item_id)
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
    current_user: CurrentPrincipal,
    item_slug: str,
) -> Any:
    """Get a prompt block by slug."""
    try:
        statement = select(PromptBlock).where(PromptBlock.slug == item_slug)
        visibility = PromptsController.visibility_filter(PromptBlock, current_user)
        if visibility is not None:
            statement = statement.where(visibility)
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
    current_user: CurrentWriter,
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
    current_user: CurrentWriter,
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
    current_user: CurrentWriter,
    item_id: int,
) -> ResponseMessage:
    """Delete a prompt block."""
    try:
        block = PromptsController.get_block_for_user(session, current_user, item_id)
        if block.templates:
            raise HTTPException(
                status_code=409, detail="Prompt block is used by a template"
            )
        session.delete(block)
        session.commit()
        return ResponseMessage(success=True, msg="Prompt block deleted successfully")
    except HTTPException:
        raise
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)
