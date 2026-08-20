"""Prompt template routes."""

from typing import Annotated, Any, Optional, Union, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import selectinload
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
from promt_engine_service.db_models.prompts import PromptTemplate, TemplateBlock
from promt_engine_service.schemas.list_params import (
    PROMPT_TEMPLATE_LIST_VOCABULARY,
    MAX_PAGE_SIZE,
    MAX_SEARCH_LENGTH,
    PromptTemplateSearchParam,
    PromptTemplateSortParam,
    SortOrderParam,
)
from promt_engine_service.schemas.prompts import (
    DynamicBlock,
    PromptTemplateModel,
    PromptTemplatesList,
)

# Router floor: authentication — same rationale as ``prompt_blocks``. The read
# routes admit the ``USER`` tier (public templates only); everything that
# mutates a template or its block list carries ``CurrentWriter`` explicitly,
# including the three that do so behind a ``GET``/``DELETE`` verb.
router = APIRouter(
    prefix="/prompt-template",
    tags=["prompt-template"],
    dependencies=[Depends(get_current_user)],
)
# pylint: disable=not-callable,broad-exception-caught


@router.get(
    "/",
    response_model=PromptTemplatesList,
    responses=BaseController.get_error_responses(),
)
def prompt_template_list(
    session: SessionDep,
    current_user: CurrentPrincipal,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 100,
    q: Annotated[str, Query(max_length=MAX_SEARCH_LENGTH)] = "",
    csrc: PromptTemplateSearchParam = None,
    sort: PromptTemplateSortParam = None,
    order: SortOrderParam = None,
    f: Annotated[
        str,
        Query(
            max_length=MAX_SEARCH_LENGTH,
            description=(
                "Comma-joined facet values, combined with OR. Allowed: "
                + ", ".join(PROMPT_TEMPLATE_LIST_VOCABULARY.facets)
                + "."
            ),
        ),
    ] = "",
) -> Any:
    """Retrieve prompt templates visible to the current user.

    Same list contract as ``GET /prompt-block/``, over the template
    vocabulary, and with one addition: ``sort=block_count`` orders by how many
    blocks a template carries, answered by a correlated subquery. The template
    table offers that column to the user, so the service answers it rather
    than leaving the control to sort one page against itself.

    ``count`` is the count of the **filtered** set. With none of the new
    parameters present the response is what ``skip``/``limit`` always
    returned.
    """
    try:
        statement = select(PromptTemplate).options(
            selectinload(cast(Any, PromptTemplate.blocks)).selectinload(
                cast(Any, TemplateBlock.block)
            )
        )
        count_statement = select(func.count()).select_from(PromptTemplate)
        predicates = ListQueryController.prompt_template_predicates(q=q, csrc=csrc, f=f)
        visibility = PromptsController.visibility_filter(PromptTemplate, current_user)
        if visibility is not None:
            predicates.append(visibility)
        for predicate in predicates:
            statement = statement.where(predicate)
            count_statement = count_statement.where(predicate)
        if sort is not None:
            statement = statement.order_by(
                ListQueryController.order_clause(
                    ListQueryController.TEMPLATE_SORT_COLUMNS, sort, order
                )
            )
        statement = statement.offset(skip).limit(limit)
        items = session.exec(statement).all()
        return PromptTemplatesList(
            count=session.exec(count_statement).one(),
            data=PromptsController.dump_prompt_templates(items),
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
def get_prompt_template(
    session: SessionDep, current_user: CurrentPrincipal, item_id: int
) -> Any:
    """Get a prompt template by ID."""
    try:
        template = PromptsController.get_readable_template(
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
    current_user: CurrentPrincipal,
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
        visibility = PromptsController.visibility_filter(PromptTemplate, current_user)
        if visibility is not None:
            statement = statement.where(visibility)
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
    session: SessionDep, current_user: CurrentPrincipal, item_id: int
) -> Any:
    """Get ordered blocks for a prompt template."""
    try:
        template = PromptsController.get_readable_template(
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
    current_user: CurrentPrincipal,
    item_id: int,
    dynamic_content: Optional[list[DynamicBlock]] = None,
) -> Any:
    """Compose a prompt template into a deterministic prompt string."""
    try:
        template = PromptsController.get_readable_template(
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
    current_user: CurrentWriter,
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
    current_user: CurrentWriter,
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
    session: SessionDep, current_user: CurrentWriter, item_id: int
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


# --------------------------------------------------------------------------
# Template block membership.
#
# `H3`/`C5`: attaching a block and moving one are state changes, and they were
# reachable by ``GET`` — which makes them cacheable, prefetchable and
# link-followable. `POST` and `PUT` below are the real verbs. The `GET` forms
# remain mounted, marked deprecated, for one minor so a client mid-flight is
# not broken by the fix; they delegate to the same body rather than carrying a
# second copy of it, so the two verbs cannot drift while both are live.
# --------------------------------------------------------------------------


@router.post(
    "/{template_id}/add-block/{block_id}/",
    response_model=ResponseModelBase,
    responses=BaseController.get_error_responses(),
)
def add_block_to_prompt_template(
    *,
    session: SessionDep,
    current_user: CurrentWriter,
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
    "/{template_id}/add-block/{block_id}/",
    response_model=ResponseModelBase,
    responses=BaseController.get_error_responses(),
    deprecated=True,
)
def add_block_to_prompt_template_via_get(
    *,
    session: SessionDep,
    current_user: CurrentWriter,
    block_id: int,
    template_id: int,
    position: int = 0,
) -> Any:
    """Deprecated ``GET`` alias of the ``POST`` above. Use ``POST``.

    Mounted only so a consumer released before `C5` keeps working; scheduled
    for removal in the next minor.
    """
    return add_block_to_prompt_template(
        session=session,
        current_user=current_user,
        block_id=block_id,
        template_id=template_id,
        position=position,
    )


@router.put(
    "/{template_id}/set-block-position/{block_id}/",
    response_model=ResponseModelBase,
    responses=BaseController.get_error_responses(),
)
def update_prompt_template_block_position(
    *,
    session: SessionDep,
    current_user: CurrentWriter,
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


@router.get(
    "/{template_id}/set-block-position/{block_id}/",
    response_model=ResponseModelBase,
    responses=BaseController.get_error_responses(),
    deprecated=True,
)
def update_prompt_template_block_position_via_get(
    *,
    session: SessionDep,
    current_user: CurrentWriter,
    block_id: int,
    template_id: int,
    position: int = 1,
) -> Any:
    """Deprecated ``GET`` alias of the ``PUT`` above. Use ``PUT``.

    Mounted only so a consumer released before `C5` keeps working; scheduled
    for removal in the next minor.
    """
    return update_prompt_template_block_position(
        session=session,
        current_user=current_user,
        block_id=block_id,
        template_id=template_id,
        position=position,
    )


@router.delete(
    "/{template_id}/delete-block/{block_id}/",
    response_model=ResponseMessage,
    responses=BaseController.get_error_responses(),
)
def delete_block_from_prompt_template(
    *,
    session: SessionDep,
    current_user: CurrentWriter,
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
