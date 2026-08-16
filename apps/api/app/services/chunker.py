from typing import TypeVar

from dataclasses import dataclass

from app.services.parser import BBox, ParsedBlock, ParsedDocument, ParsedPage

__all__ = [
    "BBox",
    "ChunkDraft",
    "ParsedBlock",
    "ParsedDocument",
    "ParsedPage",
    "chunk_pages",
]

T = TypeVar("T")


@dataclass
class ChunkDraft:
    page_number: int
    content: str
    modality: str
    bbox: BBox | None
    token_count: int
    chunk_index: int


def _union_bbox(boxes: list[BBox | None]) -> BBox | None:
    valid = [box for box in boxes if box is not None]
    if not valid:
        return None
    x0 = min(box.x for box in valid)
    y0 = min(box.y for box in valid)
    x1 = max(box.x + box.w for box in valid)
    y1 = max(box.y + box.h for box in valid)
    return BBox(x=x0, y=y0, w=x1 - x0, h=y1 - y0)


def _windows(items: list[T], target: int, overlap: int) -> list[list[T]]:
    if not items:
        return []
    if len(items) <= target:
        return [items]
    step = max(target - overlap, 1)
    result: list[list[T]] = []
    start = 0
    while start < len(items):
        end = min(start + target, len(items))
        result.append(items[start:end])
        if end == len(items):
            break
        start += step
    return result


def chunk_pages(
    pages: list[ParsedPage],
    target_tokens: int = 400,
    overlap_tokens: int = 80,
) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    chunk_index = 0
    for page in pages:
        pending: list[tuple[str, BBox | None]] = []

        def flush_text() -> None:
            nonlocal chunk_index, pending
            for window in _windows(pending, target_tokens, overlap_tokens):
                content = " ".join(token for token, _bbox in window)
                drafts.append(
                    ChunkDraft(
                        page_number=page.page_number,
                        content=content,
                        modality="text",
                        bbox=_union_bbox([bbox for _token, bbox in window]),
                        token_count=len(window),
                        chunk_index=chunk_index,
                    )
                )
                chunk_index += 1
            pending = []

        for block in page.blocks:
            if block.modality == "image":
                continue
            if block.modality == "table":
                flush_text()
                tokens = block.text.split()
                if not tokens:
                    continue
                drafts.append(
                    ChunkDraft(
                        page_number=page.page_number,
                        content=block.text.strip(),
                        modality="table",
                        bbox=block.bbox,
                        token_count=len(tokens),
                        chunk_index=chunk_index,
                    )
                )
                chunk_index += 1
                continue
            tokens = block.text.split()
            if not tokens:
                continue
            pending.extend((token, block.bbox) for token in tokens)
        flush_text()
    return drafts
