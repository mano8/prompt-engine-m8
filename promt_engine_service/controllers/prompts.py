"""Prompt domain controller."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Optional, cast

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, asc, desc, func, or_
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from promt_engine_service.core.deps import has_reader_privileges
from promt_engine_service.db_models.categories import Category
from promt_engine_service.db_models.prompts import (
    PromptBlock,
    PromptTemplate,
    TemplateBlock,
)
from promt_engine_service.schemas.base import PromptBlockType
from promt_engine_service.schemas.list_params import (
    FACET_SEPARATOR,
    CategorySearchField,
    CategorySortField,
    ListSortOrder,
    PromptBlockFacet,
    PromptBlockSearchField,
    PromptBlockSortField,
    PromptTemplateFacet,
    PromptTemplateSearchField,
    PromptTemplateSortField,
)
from promt_engine_service.schemas.prompts import (
    DynamicBlock,
    PromptBlockModel,
    TemplateBlockDict,
    PromptTemplateDict,
    PromptTemplateModel,
)

DYNAMIC_CONTENT_PLACEHOLDER = "{{dynamic_content}}"


def render_dynamic_block_content(block_content: str, user_content: str) -> str:
    """Render authored dynamic block content with caller-supplied content.

    Only dynamic blocks interpret DYNAMIC_CONTENT_PLACEHOLDER. Dynamic blocks
    without the placeholder keep the legacy behavior where caller content
    replaces the whole block.
    """
    if DYNAMIC_CONTENT_PLACEHOLDER not in block_content:
        return user_content
    return block_content.replace(DYNAMIC_CONTENT_PLACEHOLDER, user_content)


class PromptsController:
    """Prompt block and template operations."""

    @staticmethod
    def _owns(record: Any, current_user: Any) -> bool:
        return bool(getattr(current_user, "is_superuser", False)) or str(
            record.owner_id
        ) == str(current_user.id)

    @staticmethod
    def _require_owner(record: Any, current_user: Any) -> None:
        if not PromptsController._owns(record, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

    @staticmethod
    def _is_visible(record: Any, current_user: Any) -> bool:
        """Return whether *current_user* may read *record*.

        Reads are wider than writes: a public record is readable by any
        authenticated principal, down to and including the ``USER`` tier, while
        a private one stays owner-only. Writes never consult this — they go
        through ``_require_owner``, so a writer cannot edit someone else's
        record just because it is public.
        """
        return PromptsController._owns(record, current_user) or bool(record.is_public)

    @staticmethod
    def _require_visible(record: Any, current_user: Any) -> None:
        if not PromptsController._is_visible(record, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

    @staticmethod
    def visibility_filter(
        model: Any, current_user: Any
    ) -> Optional[ColumnElement[bool]]:
        """Return the read predicate for *model* rows, or ``None`` for no filter.

        The single place the read tiers are expressed:

        * superuser — every row, no predicate;
        * ``READER`` and above — rows they own, plus public rows;
        * ``USER`` — public rows only.

        Monotone in privilege on purpose: a reader must never see less than the
        tier below it, so the reader predicate is a superset of the user one.
        """
        if getattr(current_user, "is_superuser", False):
            return None
        if has_reader_privileges(current_user):
            return or_(
                model.owner_id == current_user.id,
                model.is_public.is_(True),
            )
        return model.is_public.is_(True)

    @staticmethod
    def _load_block(session: Session, block_id: int) -> PromptBlock:
        block = session.get(PromptBlock, block_id)
        if block is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Prompt block not found"
            )
        return block

    @staticmethod
    def get_block_for_user(
        session: Session, current_user: Any, block_id: int
    ) -> PromptBlock:
        """Load a prompt block and enforce ownership. Write path."""
        block = PromptsController._load_block(session, block_id)
        PromptsController._require_owner(block, current_user)
        return block

    @staticmethod
    def get_readable_block(
        session: Session, current_user: Any, block_id: int
    ) -> PromptBlock:
        """Load a prompt block the caller may read. Read path."""
        block = PromptsController._load_block(session, block_id)
        PromptsController._require_visible(block, current_user)
        return block

    @staticmethod
    def _load_template(session: Session, template_id: int) -> PromptTemplate:
        template = session.exec(
            select(PromptTemplate)
            .where(PromptTemplate.id == template_id)
            .options(
                selectinload(cast(Any, PromptTemplate.blocks)).selectinload(
                    cast(Any, TemplateBlock.block)
                )
            )
        ).first()
        if template is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prompt template not found",
            )
        return template

    @staticmethod
    def get_template_for_user(
        session: Session, current_user: Any, template_id: int
    ) -> PromptTemplate:
        """Load a prompt template with blocks and enforce ownership. Write path."""
        template = PromptsController._load_template(session, template_id)
        PromptsController._require_owner(template, current_user)
        return template

    @staticmethod
    def get_readable_template(
        session: Session, current_user: Any, template_id: int
    ) -> PromptTemplate:
        """Load a prompt template the caller may read. Read path."""
        template = PromptsController._load_template(session, template_id)
        PromptsController._require_visible(template, current_user)
        return template

    @staticmethod
    def dump_prompt_templates(
        templates: Iterable[PromptTemplate],
    ) -> list[PromptTemplateDict]:
        """Serialize prompt templates."""
        return [
            PromptsController.dump_prompt_template(template) for template in templates
        ]

    @staticmethod
    def dump_prompt_template(template: PromptTemplate) -> PromptTemplateDict:
        """Serialize a prompt template with ordered blocks."""
        return {
            "id": template.id,
            "name": template.name,
            "slug": template.slug,
            "description": template.description,
            "is_public": template.is_public,
            "blocks": PromptsController.dump_template_blocks(template.blocks),
        }

    @staticmethod
    def dump_template_blocks(
        blocks: Iterable[TemplateBlock],
    ) -> list[TemplateBlockDict]:
        """Serialize template blocks in stable position order."""
        return [
            PromptsController.dump_template_block(block)
            for block in sorted(blocks, key=lambda item: item.position)
        ]

    @staticmethod
    def dump_template_block(block: TemplateBlock) -> TemplateBlockDict:
        """Serialize a template-block join without leaking unrelated owner data."""
        return {
            "id": block.id,
            "block_id": block.block_id,
            "template_id": block.template_id,
            "name": block.block.name,
            "slug": block.block.slug,
            "description": block.block.description,
            "content": block.block.content,
            "type": block.block.type.value,
            "is_dynamic": block.block.is_dynamic,
            "is_public": block.block.is_public,
            "position": block.position,
        }

    @staticmethod
    def compose_prompt_content(
        template: PromptTemplate,
        dynamic_content: Optional[list[DynamicBlock]],
    ) -> str:
        """Compose a deterministic prompt string from ordered template blocks."""
        dynamic_by_id = {item.id: item.content for item in dynamic_content or []}
        contents: list[str] = []
        for template_block in sorted(template.blocks, key=lambda item: item.position):
            block = template_block.block
            if block.is_dynamic:
                content = dynamic_by_id.get(block.id)
                if content is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Dynamic content is required for block {block.id}:{block.name}",
                    )
                contents.append(render_dynamic_block_content(block.content, content))
            else:
                contents.append(block.content)
        return "\n\n".join(contents)

    @staticmethod
    def create_prompt_block(
        *, session: Session, current_user: Any, item_in: PromptBlockModel
    ) -> PromptBlock:
        """Create a prompt block owned by the current user."""
        block = PromptBlock.model_validate(
            item_in.model_dump(),
            update={"owner_id": str(current_user.id)},
        )
        session.add(block)
        session.commit()
        session.refresh(block)
        return block

    @staticmethod
    def update_prompt_block(
        *,
        session: Session,
        current_user: Any,
        item_id: int,
        item_in: PromptBlockModel,
    ) -> PromptBlock:
        """Update a prompt block after ownership validation."""
        block = PromptsController.get_block_for_user(session, current_user, item_id)
        block.sqlmodel_update(item_in.model_dump(exclude_unset=True))
        session.add(block)
        session.commit()
        session.refresh(block)
        return block

    @staticmethod
    def create_prompt_template(
        *,
        session: Session,
        current_user: Any,
        item_in: PromptTemplateModel,
    ) -> PromptTemplate:
        """Create a prompt template owned by the current user."""
        template = PromptTemplate.model_validate(
            item_in.model_dump(),
            update={"owner_id": str(current_user.id)},
        )
        session.add(template)
        session.commit()
        session.refresh(template)
        return template

    @staticmethod
    def update_prompt_template(
        *,
        session: Session,
        current_user: Any,
        item_id: int,
        item_in: PromptTemplateModel,
    ) -> PromptTemplate:
        """Update a prompt template after ownership validation."""
        template = PromptsController.get_template_for_user(
            session, current_user, item_id
        )
        template.sqlmodel_update(item_in.model_dump(exclude_unset=True))
        session.add(template)
        session.commit()
        session.refresh(template)
        return template

    @staticmethod
    def add_template_block_and_reorder(
        *,
        session: Session,
        current_user: Any,
        template_id: int,
        block_id: int,
        position: int = 0,
    ) -> TemplateBlock:
        """Add a block to a template and keep positions contiguous."""
        template = PromptsController.get_template_for_user(
            session, current_user, template_id
        )
        block = PromptsController.get_block_for_user(session, current_user, block_id)

        if any(item.block_id == block.id for item in template.blocks):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Block already exists in template",
            )

        ordered_blocks = sorted(template.blocks, key=lambda item: item.position)
        if position <= 0 or position > len(ordered_blocks) + 1:
            position = len(ordered_blocks) + 1

        for item in reversed(ordered_blocks):
            if item.position >= position:
                item.position += 1
                session.add(item)
                session.flush()

        template_block = TemplateBlock(
            template_id=template.id, block_id=block.id, position=position
        )
        session.add(template_block)
        session.commit()
        session.refresh(template_block)
        return template_block

    @staticmethod
    def update_template_block_position(
        *,
        session: Session,
        current_user: Any,
        template_id: int,
        block_id: int,
        new_position: int,
    ) -> TemplateBlock:
        """Move a template block and normalize all positions."""
        template = PromptsController.get_template_for_user(
            session, current_user, template_id
        )
        blocks = sorted(template.blocks, key=lambda item: item.position)
        current_block = next(
            (item for item in blocks if item.block_id == block_id), None
        )
        if current_block is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Block not found in template",
            )
        if new_position < 1 or new_position > len(blocks):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid position"
            )

        blocks.remove(current_block)
        blocks.insert(new_position - 1, current_block)
        for index, item in enumerate(blocks, start=1):
            item.position = -index
            session.add(item)
        session.flush()
        for index, item in enumerate(blocks, start=1):
            item.position = index
            session.add(item)
        session.commit()
        session.refresh(current_block)
        return current_block

    @staticmethod
    def delete_template_block_and_reorder(
        *,
        session: Session,
        current_user: Any,
        template_id: int,
        block_id: int,
    ) -> None:
        """Remove a block from a template and normalize positions."""
        template = PromptsController.get_template_for_user(
            session, current_user, template_id
        )
        block_to_remove = next(
            (item for item in template.blocks if item.block_id == block_id), None
        )
        if block_to_remove is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Block not found in template",
            )

        session.delete(block_to_remove)
        session.flush()
        remaining_blocks = sorted(
            (item for item in template.blocks if item.block_id != block_id),
            key=lambda item: item.position,
        )
        for index, item in enumerate(remaining_blocks, start=1):
            item.position = index
            session.add(item)
        session.commit()


#: Number of blocks attached to a template, as a correlated subquery so
#: ``sort=block_count`` can be answered in SQL instead of in the browser.
_TEMPLATE_BLOCK_COUNT = (
    select(func.count(cast(Any, TemplateBlock.id)))  # pylint: disable=not-callable
    .where(cast(Any, TemplateBlock.template_id) == PromptTemplate.id)
    .correlate(cast(Any, PromptTemplate))
    .scalar_subquery()
)


class ListQueryController:
    """Turn the declared list vocabulary into SQL, for all three list routes.

    The maps below are the only bridge between a caller-supplied name and a
    column: a value that is not a key here never reaches the query, and one
    that is reaches it as a column object rather than as text. Free-text ``q``
    is bound as a parameter. That is what makes ``q``/``csrc``/``sort``/``f``
    safe to accept at the trust boundary (`SEC-VALIDATE-UNTRUSTED-INPUT`).

    Keeping all three resources here — rather than one map per route module —
    is deliberate: three copies of an allow-list drift, and a drifted
    allow-list is indistinguishable from a missing one until something is
    already wrong.
    """

    BLOCK_SEARCH_COLUMNS: dict[PromptBlockSearchField, Any] = {
        PromptBlockSearchField.NAME: PromptBlock.name,
        PromptBlockSearchField.SLUG: PromptBlock.slug,
        PromptBlockSearchField.DESCRIPTION: PromptBlock.description,
        PromptBlockSearchField.CONTENT: PromptBlock.content,
    }
    BLOCK_SORT_COLUMNS: dict[PromptBlockSortField, Any] = {
        PromptBlockSortField.ID: PromptBlock.id,
        PromptBlockSortField.NAME: PromptBlock.name,
        PromptBlockSortField.SLUG: PromptBlock.slug,
        PromptBlockSortField.TYPE: PromptBlock.type,
        PromptBlockSortField.IS_DYNAMIC: PromptBlock.is_dynamic,
        PromptBlockSortField.IS_PUBLIC: PromptBlock.is_public,
        PromptBlockSortField.CREATED_AT: PromptBlock.created_at,
        PromptBlockSortField.UPDATED_AT: PromptBlock.updated_at,
    }
    BLOCK_FACET_PREDICATES: dict[PromptBlockFacet, Any] = {
        PromptBlockFacet.ROLE: PromptBlock.type == PromptBlockType.ROLE,
        PromptBlockFacet.TASK: PromptBlock.type == PromptBlockType.TASK,
        PromptBlockFacet.CONTEXT: PromptBlock.type == PromptBlockType.CONTEXT,
        PromptBlockFacet.INSTRUCTION: PromptBlock.type == PromptBlockType.INSTRUCTION,
        PromptBlockFacet.EXAMPLE: PromptBlock.type == PromptBlockType.EXAMPLE,
        PromptBlockFacet.FORMAT: PromptBlock.type == PromptBlockType.FORMAT,
        PromptBlockFacet.DYNAMIC: cast(Any, PromptBlock.is_dynamic).is_(True),
        PromptBlockFacet.STATIC: cast(Any, PromptBlock.is_dynamic).is_(False),
        PromptBlockFacet.PUBLIC: cast(Any, PromptBlock.is_public).is_(True),
        PromptBlockFacet.PRIVATE: cast(Any, PromptBlock.is_public).is_(False),
    }

    TEMPLATE_SEARCH_COLUMNS: dict[PromptTemplateSearchField, Any] = {
        PromptTemplateSearchField.NAME: PromptTemplate.name,
        PromptTemplateSearchField.SLUG: PromptTemplate.slug,
        PromptTemplateSearchField.DESCRIPTION: PromptTemplate.description,
    }
    TEMPLATE_SORT_COLUMNS: dict[PromptTemplateSortField, Any] = {
        PromptTemplateSortField.ID: PromptTemplate.id,
        PromptTemplateSortField.NAME: PromptTemplate.name,
        PromptTemplateSortField.SLUG: PromptTemplate.slug,
        PromptTemplateSortField.IS_PUBLIC: PromptTemplate.is_public,
        PromptTemplateSortField.BLOCK_COUNT: _TEMPLATE_BLOCK_COUNT,
        PromptTemplateSortField.CREATED_AT: PromptTemplate.created_at,
        PromptTemplateSortField.UPDATED_AT: PromptTemplate.updated_at,
    }
    TEMPLATE_FACET_PREDICATES: dict[PromptTemplateFacet, Any] = {
        PromptTemplateFacet.PUBLIC: cast(Any, PromptTemplate.is_public).is_(True),
        PromptTemplateFacet.PRIVATE: cast(Any, PromptTemplate.is_public).is_(False),
    }

    CATEGORY_SEARCH_COLUMNS: dict[CategorySearchField, Any] = {
        CategorySearchField.NAME: Category.name,
        CategorySearchField.SLUG: Category.slug,
    }
    CATEGORY_SORT_COLUMNS: dict[CategorySortField, Any] = {
        CategorySortField.ID: Category.id,
        CategorySortField.NAME: Category.name,
        CategorySortField.SLUG: Category.slug,
        CategorySortField.TYPE: Category.type,
        CategorySortField.CREATED_AT: Category.created_at,
        CategorySortField.UPDATED_AT: Category.updated_at,
    }

    @staticmethod
    def search_predicate(
        columns: dict[Any, Any],
        q: str,
        csrc: Optional[Any] = None,
    ) -> Optional[ColumnElement[bool]]:
        """Match *q* case-insensitively, in one column or across them all.

        The term is lowered on both sides so the result does not depend on the
        database's collation, and it is passed to ``contains`` — a bound
        parameter with ``%``/``_`` escaped — never formatted into SQL.
        """
        term = q.strip().lower()
        if not term:
            return None
        selected = [columns[csrc]] if csrc is not None else list(columns.values())
        return or_(
            *(func.lower(column).contains(term, autoescape=True) for column in selected)
        )

    @staticmethod
    def parse_facets(raw: str, facet_type: Any, resource: str) -> list[Any]:
        """Resolve ``f`` into declared facet members, rejecting anything else.

        Empty segments are dropped rather than rejected, so the empty default a
        faceted-filter control sends means "no filter". Any other undeclared
        value is a ``422``: a silently ignored filter renders a control that
        does nothing, which is the failure this contract exists to remove.
        """
        selected: list[Any] = []
        for chunk in raw.split(FACET_SEPARATOR):
            name = chunk.strip()
            if not name:
                continue
            try:
                member = facet_type(name)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=(
                        f"Unknown {resource} filter value {name!r}. "
                        f"Allowed: {', '.join(item.value for item in facet_type)}."
                    ),
                ) from None
            if member not in selected:
                selected.append(member)
        return selected

    @staticmethod
    def facet_predicate(
        facets: list[Any], predicates: dict[Any, Any]
    ) -> Optional[ColumnElement[bool]]:
        """Combine selected facets with ``OR``, matching the filter control."""
        if not facets:
            return None
        return or_(*(predicates[facet] for facet in facets))

    @staticmethod
    def order_clause(
        columns: dict[Any, Any], sort: Any, order: Optional[ListSortOrder]
    ) -> Any:
        """Return the ``ORDER BY`` clause for an allow-listed column.

        ``order`` is optional because a caller may name a column without naming
        a direction; ascending is the direction a table header shows on its
        first click, so it is the one an unstated ``order`` means.
        """
        column = columns[sort]
        return desc(column) if order is ListSortOrder.DESC else asc(column)

    @classmethod
    def prompt_block_predicates(
        cls,
        *,
        q: str,
        csrc: Optional[PromptBlockSearchField],
        f: str,
    ) -> list[ColumnElement[bool]]:
        """Search and facet predicates for ``GET /prompt-block/``."""
        return cls._predicates(
            search_columns=cls.BLOCK_SEARCH_COLUMNS,
            facet_predicates=cls.BLOCK_FACET_PREDICATES,
            facet_type=PromptBlockFacet,
            resource="prompt-block",
            q=q,
            csrc=csrc,
            f=f,
        )

    @classmethod
    def prompt_template_predicates(
        cls,
        *,
        q: str,
        csrc: Optional[PromptTemplateSearchField],
        f: str,
    ) -> list[ColumnElement[bool]]:
        """Search and facet predicates for ``GET /prompt-template/``."""
        return cls._predicates(
            search_columns=cls.TEMPLATE_SEARCH_COLUMNS,
            facet_predicates=cls.TEMPLATE_FACET_PREDICATES,
            facet_type=PromptTemplateFacet,
            resource="prompt-template",
            q=q,
            csrc=csrc,
            f=f,
        )

    @classmethod
    def category_predicates(cls, *, q: str) -> list[ColumnElement[bool]]:
        """Search predicates for ``GET /category/``.

        The category endpoint declares no ``csrc`` and no facets, so ``q``
        always scans the declared category columns.
        """
        search = cls.search_predicate(cls.CATEGORY_SEARCH_COLUMNS, q)
        return [] if search is None else [search]

    @classmethod
    def _predicates(
        cls,
        *,
        search_columns: dict[Any, Any],
        facet_predicates: dict[Any, Any],
        facet_type: Any,
        resource: str,
        q: str,
        csrc: Optional[Any],
        f: str,
    ) -> list[ColumnElement[bool]]:
        predicates: list[ColumnElement[bool]] = []
        search = cls.search_predicate(search_columns, q, csrc)
        if search is not None:
            predicates.append(search)
        facets = cls.facet_predicate(
            cls.parse_facets(f, facet_type, resource), facet_predicates
        )
        if facets is not None:
            predicates.append(facets)
        return predicates


# Backwards-compatible name for existing imports/tests that used the typo.
PromtsController = PromptsController
