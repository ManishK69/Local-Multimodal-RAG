from dataclasses import dataclass, field
from pathlib import Path

import pymupdf as fitz

from app.services.hashing import sha256_bytes


@dataclass(frozen=True)
class BBox:
    x: float
    y: float
    w: float
    h: float

    def as_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


@dataclass
class ParsedBlock:
    text: str
    modality: str
    bbox: BBox | None
    image_bytes: bytes | None


@dataclass
class ParsedPage:
    page_number: int
    width_pt: float
    height_pt: float
    blocks: list[ParsedBlock]


@dataclass
class ParsedDocument:
    pages: list[ParsedPage] = field(default_factory=list)


def _rect_to_bbox(rect: tuple[float, float, float, float] | fitz.Rect) -> BBox:
    x0, y0, x1, y1 = float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])
    return BBox(x=x0, y=y0, w=max(x1 - x0, 0.0), h=max(y1 - y0, 0.0))


def _block_text(block: dict) -> str:
    lines: list[str] = []
    for line in block.get("lines", []):
        spans = [str(span.get("text") or "") for span in line.get("spans", [])]
        lines.append("".join(spans))
    return "\n".join(lines).strip()


def _extract_image_bytes(
    document: fitz.Document, page: fitz.Page, block: dict
) -> bytes | None:
    raw = block.get("image")
    if isinstance(raw, (bytes, bytearray)):
        if bytes(raw[:8]) == b"\x89PNG\r\n\x1a\n":
            return bytes(raw)
        try:
            pix = fitz.Pixmap(raw)
            if pix.n - pix.alpha > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            return pix.tobytes("png")
        except Exception:
            return None
    xref = block.get("xref") or block.get("number")
    if not xref:
        return None
    try:
        pix = fitz.Pixmap(document, int(xref))
        if pix.n - pix.alpha > 3:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        return pix.tobytes("png")
    except Exception:
        return None


def parse_pdf(path: Path) -> ParsedDocument:
    document = fitz.open(path)
    try:
        pages: list[ParsedPage] = []
        for index, page in enumerate(document, start=1):
            blocks: list[ParsedBlock] = []
            payload = page.get_text("dict")
            for block in payload.get("blocks", []):
                bbox = _rect_to_bbox(block["bbox"]) if block.get("bbox") else None
                if block.get("type") == 1:
                    image_bytes = _extract_image_bytes(document, page, block)
                    blocks.append(
                        ParsedBlock(
                            text="",
                            modality="image",
                            bbox=bbox,
                            image_bytes=image_bytes,
                        )
                    )
                    continue
                text = _block_text(block)
                if not text:
                    continue
                blocks.append(
                    ParsedBlock(
                        text=text,
                        modality="text",
                        bbox=bbox,
                        image_bytes=None,
                    )
                )
            try:
                for table in page.find_tables().tables:
                    markdown = table.to_markdown()
                    if not markdown or not markdown.strip():
                        continue
                    blocks.append(
                        ParsedBlock(
                            text=markdown.strip(),
                            modality="table",
                            bbox=_rect_to_bbox(table.bbox),
                            image_bytes=None,
                        )
                    )
            except Exception:
                pass
            pages.append(
                ParsedPage(
                    page_number=index,
                    width_pt=float(page.rect.width),
                    height_pt=float(page.rect.height),
                    blocks=blocks,
                )
            )
        return ParsedDocument(pages=pages)
    finally:
        document.close()


def image_manifest(parsed: ParsedDocument) -> list[dict]:
    images: list[dict] = []
    for page in parsed.pages:
        for block in page.blocks:
            if block.modality != "image" or not block.image_bytes:
                continue
            digest = sha256_bytes(block.image_bytes)
            images.append(
                {
                    "page_number": page.page_number,
                    "bbox": block.bbox.as_dict() if block.bbox else None,
                    "sha256": digest,
                    "bytes": block.image_bytes,
                }
            )
    return images
