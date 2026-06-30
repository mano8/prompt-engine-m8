"""Prompt domain controller."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from promt_engine_service.db_models.prompts import PromptBlock, PromptTemplate, TemplateBlock
from promt_engine_service.schemas.prompts import DynamicBlock, PromptBlockModel, PromptTemplateModel


class PromptsController:
    """Prompt block and template operations."""

    @staticmethod
    def _owns(record: Any, current_user: Any) -> bool:
        return bool(getattr(current_user, "is_superuser", False)) or str(record.owner_id) == str(current_user.id)

    @staticmethod
    def _require_owner(record: Any, current_user: Any) -> None:
        if not PromptsController._owns(record, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

    @staticmethod
    def get_block_for_user(session: Session, current_user: Any, block_id: int) -> PromptBlock:
        """Load a prompt block and enforce ownership."""
        block = session.get(PromptBlock, block_id)
        if block is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt block not found")
        PromptsController._require_owner(block, current_user)
        return block

    @staticmethod
    def get_template_for_user(session: Session, current_user: Any, template_id: int) -> PromptTemplate:
        """Load a prompt template with blocks and enforce ownership."""
        template = session.exec(
            select(PromptTemplate)
            .where(PromptTemplate.id == template_id)
            .options(selectinload(PromptTemplate.blocks).selectinload(TemplateBlock.block))
        ).first()
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt template not found")
        PromptsController._require_owner(template, current_user)
        return template

    @staticmethod
    def dump_prompt_templates(templates: Iterable[PromptTemplate]) -> list[dict[str, Any]]:
        """Serialize prompt templates."""
        return [PromptsController.dump_prompt_template(template) for template in templates]

    @staticmethod
    def dump_prompt_template(template: PromptTemplate) -> dict[str, Any]:
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
    def dump_template_blocks(blocks: Iterable[TemplateBlock]) -> list[dict[str, Any]]:
        """Serialize template blocks in stable position order."""
        return [
            PromptsController.dump_template_block(block)
            for block in sorted(blocks, key=lambda item: item.position)
        ]

    @staticmethod
    def dump_template_block(block: TemplateBlock) -> dict[str, Any]:
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
                contents.append(content)
            else:
                contents.append(block.content)
        return "\n\n".join(contents)

    @staticmethod
    def create_prompt_block(*, session: Session, current_user: Any, item_in: PromptBlockModel) -> PromptBlock:
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
        template = PromptsController.get_template_for_user(session, current_user, item_id)
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
        template = PromptsController.get_template_for_user(session, current_user, template_id)
        block = PromptsController.get_block_for_user(session, current_user, block_id)

        if any(item.block_id == block.id for item in template.blocks):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Block already exists in template")

        ordered_blocks = sorted(template.blocks, key=lambda item: item.position)
        if position <= 0 or position > len(ordered_blocks) + 1:
            position = len(ordered_blocks) + 1

        for item in reversed(ordered_blocks):
            if item.position >= position:
                item.position += 1
                session.add(item)
                session.flush()

        template_block = TemplateBlock(template_id=template.id, block_id=block.id, position=position)
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
        template = PromptsController.get_template_for_user(session, current_user, template_id)
        blocks = sorted(template.blocks, key=lambda item: item.position)
        current_block = next((item for item in blocks if item.block_id == block_id), None)
        if current_block is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found in template")
        if new_position < 1 or new_position > len(blocks):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid position")

        blocks.remove(current_block)
        blocks.insert(new_position - 1, current_block)
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
        template = PromptsController.get_template_for_user(session, current_user, template_id)
        block_to_remove = next((item for item in template.blocks if item.block_id == block_id), None)
        if block_to_remove is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found in template")

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


# Backwards-compatible name for existing imports/tests that used the typo.
PromtsController = PromptsController