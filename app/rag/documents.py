from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from app.errors import UnsupportedFileTypeError


@dataclass
class ParsedDocument:
    text: str
    page_count: int
    page_offsets: list[tuple[int, int, int]]
    file_type: str


def calculate_checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_document(content: bytes, filename: str) -> ParsedDocument:
    suffix = Path(filename).suffix.lower()

    if suffix == ".pdf":
        return _parse_pdf(content)
    if suffix in {".md", ".markdown"}:
        return _parse_text(content, file_type="markdown")
    if suffix == ".txt":
        return _parse_text(content, file_type="txt")

    raise UnsupportedFileTypeError(f"不支持的文件类型：{suffix or 'unknown'}")


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _parse_text(content: bytes, *, file_type: str) -> ParsedDocument:
    text = normalize_text(_decode_text(content))
    return ParsedDocument(
        text=text,
        page_count=1,
        page_offsets=[(0, len(text), 1)],
        file_type=file_type,
    )


def _parse_pdf(content: bytes) -> ParsedDocument:
    reader = PdfReader(io.BytesIO(content))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(normalize_text(page.extract_text() or ""))

    parts: list[str] = []
    offsets: list[tuple[int, int, int]] = []
    position = 0

    for page_number, page_text in enumerate(pages, start=1):
        if parts:
            parts.append("\n\n")
            position += 2
        start = position
        parts.append(page_text)
        position += len(page_text)
        offsets.append((start, position, page_number))

    return ParsedDocument(
        text="".join(parts),
        page_count=len(pages),
        page_offsets=offsets,
        file_type="pdf",
    )


def page_for_offset(offsets: list[tuple[int, int, int]], position: int) -> int | None:
    for start, end, page_number in offsets:
        if start <= position < end:
            return page_number
    return offsets[-1][2] if offsets else None
