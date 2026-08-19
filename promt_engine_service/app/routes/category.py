"""Category api routes."""

from typing import Annotated, Any, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select
from sqlmodel import func

from promt_engine_service.app.deps import (
    CurrentReader,
    CurrentWriter,
    SessionDep,
    require_reader,
)

from promt_engine_service.controllers.prompts import ListQueryController
from promt_engine_service.db_models.categories import (
    Category,
    CategoryCreate,
    CategoryUpdate,
    CategoriesPublic,
)
from promt_engine_service.schemas.list_params import (
    MAX_SEARCH_LENGTH,
    CategorySortParam,
    SortOrderParam,
)
from fastapi_m8 import BaseController, ResponseMessage, ResponseModelBase

# Router floor: reader. A category carries no ``is_public`` column, so there is
# no public view of one — every read here is an owned read, and a route added
# later inherits that floor instead of having to remember it.
router = APIRouter(
    prefix="/category",
    tags=["category"],
    dependencies=[Depends(require_reader)],
)
# pylint: disable=broad-exception-caught, not-callable


@router.get(
    "/",
    response_model=Optional[CategoriesPublic],
    responses=BaseController.get_error_responses(),
)
async def read_root(
    session: SessionDep,
    current_user: CurrentReader,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1)] = 100,
    q: Annotated[str, Query(max_length=MAX_SEARCH_LENGTH)] = "",
    sort: CategorySortParam = None,
    order: SortOrderParam = None,
) -> Any:
    """Retrieve category list.

    ``q`` searches the declared category columns and ``sort``/``order`` order
    the page; ``count`` describes the **filtered** set. A category carries no
    public flag and no faceted axis, so this endpoint declares no ``csrc`` and
    no ``f`` — see ``CATEGORY_LIST_VOCABULARY``.

    The superuser-vs-owner split is unchanged and is applied as a predicate
    alongside the search rather than by branching the whole query, so a filter
    can never widen what a non-superuser sees.
    """
    try:
        predicates = ListQueryController.category_predicates(q=q)
        if not current_user.is_superuser:
            predicates.append(Category.owner_id == current_user.id)

        statement = select(Category)
        count_statement = select(func.count()).select_from(Category)
        for predicate in predicates:
            statement = statement.where(predicate)
            count_statement = count_statement.where(predicate)
        if sort is not None:
            statement = statement.order_by(
                ListQueryController.order_clause(
                    ListQueryController.CATEGORY_SORT_COLUMNS, sort, order
                )
            )
        statement = statement.offset(skip).limit(limit)

        return CategoriesPublic(
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
def read_item(session: SessionDep, current_user: CurrentReader, item_id: int) -> Any:
    """
    Get item by ID.
    """
    try:
        item = session.get(Category, item_id)
        if not item:
            return ResponseMessage(success=False, msg="Item not found.")
        if not current_user.is_superuser and (item.owner_id != current_user.id):
            raise HTTPException(status_code=401, detail="Not enough permissions")
        return ResponseModelBase(success=True, data=dict(item))
    except HTTPException as ex:
        raise ex
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.post(
    "/add/",
    response_model=ResponseModelBase,
    responses=BaseController.get_error_responses(),
)
def create_item(
    *, session: SessionDep, current_user: CurrentWriter, item_in: CategoryCreate
) -> Any:
    """
    Create new item.
    """
    try:
        item = Category.model_validate(item_in, update={"owner_id": current_user.id})
        session.add(item)
        session.commit()
        session.refresh(item)
        return ResponseModelBase(success=True, data=dict(item))
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.put(
    "/edit/{item_id}/",
    response_model=ResponseModelBase,
    responses=BaseController.get_error_responses(),
)
def update_item(
    *,
    session: SessionDep,
    current_user: CurrentWriter,
    item_id: int,
    item_in: CategoryUpdate,
) -> Any:
    """
    Update an item.
    """
    try:
        item = session.get(Category, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        if not current_user.is_superuser and (item.owner_id != current_user.id):
            raise HTTPException(status_code=400, detail="Not enough permissions")
        update_dict = item_in.model_dump(exclude_unset=True)
        item.sqlmodel_update(update_dict)
        session.add(item)
        session.commit()
        session.refresh(item)
        return ResponseModelBase(success=True, data=dict(item))
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)


@router.delete(
    "/delete/{item_id}/",
    response_model=ResponseMessage,
    responses=BaseController.get_error_responses(),
)
def delete_item(
    session: SessionDep, current_user: CurrentWriter, item_id: int
) -> ResponseMessage:
    """
    Delete an item.
    """
    try:
        item = session.get(Category, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        if not current_user.is_superuser and (item.owner_id != current_user.id):
            raise HTTPException(status_code=400, detail="Not enough permissions")
        session.delete(item)
        session.commit()
        return ResponseMessage(success=True, msg="Category deleted successfully")
    except Exception as ex:
        return BaseController.handle_exception(ex=ex, session=session)
