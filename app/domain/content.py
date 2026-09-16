from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ContentBlock(BaseModel):
    id: str
    kind: Literal[
        "paragraph", "title", "heading1", "heading2",
        "list_item", "table_ref",
    ] = "paragraph"
    text: str
    visible: bool = True
    keep_with_next: bool = False
    section: str = ""  # Agrupación lógica: "portada", "nota_1", "nota_4", etc.
    note_number: int | None = None  # Número de nota para headings de Memoria
    table_id: str | None = None  # Referencia a FinanceTable (cuando kind == "table_ref")


class ContentModel(BaseModel):
    blocks: list[ContentBlock] = Field(default_factory=list)

    def get(self, block_id: str) -> ContentBlock | None:
        for block in self.blocks:
            if block.id == block_id:
                return block
        return None

    def upsert(self, block: ContentBlock) -> None:
        for i, existing in enumerate(self.blocks):
            if existing.id == block.id:
                self.blocks[i] = block
                return
        self.blocks.append(block)

    def delete(self, block_id: str) -> bool:
        before = len(self.blocks)
        self.blocks = [b for b in self.blocks if b.id != block_id]
        return len(self.blocks) < before

    def insert_after(self, after_id: str | None, block: ContentBlock) -> None:
        if not after_id:
            self.blocks.append(block)
            return
        for i, existing in enumerate(self.blocks):
            if existing.id == after_id:
                self.blocks.insert(i + 1, block)
                return
        self.blocks.append(block)

    def visible_blocks(self) -> list[ContentBlock]:
        return [b for b in self.blocks if b.visible]

    def sections(self) -> list[str]:
        """Return ordered unique sections."""
        seen: set[str] = set()
        result: list[str] = []
        for b in self.blocks:
            if b.section and b.section not in seen:
                seen.add(b.section)
                result.append(b.section)
        return result

    def blocks_by_section(self, section: str) -> list[ContentBlock]:
        return [b for b in self.blocks if b.section == section]
