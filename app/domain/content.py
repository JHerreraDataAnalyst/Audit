from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ContentBlock(BaseModel):
    id: str
    kind: Literal["paragraph", "title"] = "paragraph"
    text: str


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
