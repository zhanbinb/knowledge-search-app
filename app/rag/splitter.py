from __future__ import annotations

import re
import uuid

from app.rag.documents import ParsedDocument, page_for_offset


def split_document(
    parsed: ParsedDocument,
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> list[dict]:
    text = parsed.text
    if not text:
        return []

    boundaries = _candidate_boundaries(text, chunk_size)
    pieces: list[dict] = []
    start = 0
    chunk_index = 0

    while start < len(text):
        target_end = min(start + chunk_size, len(text))
        end = target_end

        if target_end < len(text):
            possible = [item for item in boundaries if start + chunk_size // 2 < item <= target_end]
            if possible:
                end = possible[-1]
            else:
                next_newline = text.find("\n", start + chunk_size // 2, target_end + 80)
                if next_newline != -1:
                    end = min(next_newline + 1, len(text))

        while end < len(text) and text[end - 1] not in "\n。！？；.!?;":
            end += 1
            if end - start > chunk_size + 160:
                break

        content = text[start:end].strip()
        if content:
            page_number = page_for_offset(parsed.page_offsets, start)
            heading_path = _heading_path(text, start)
            pieces.append(
                {
                    "id": f"chk_{uuid.uuid4().hex}",
                    "content": content,
                    "heading_path": heading_path,
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                    "char_start": start,
                    "char_end": end,
                }
            )
            chunk_index += 1

        if end >= len(text):
            break
        next_start = max(end - chunk_overlap, start + 1)
        start = next_start

    return pieces


def _candidate_boundaries(text: str, chunk_size: int) -> list[int]:
    candidates: list[int] = []
    pattern = re.compile(r"(?:^|\n)(#{1,6}\s+[^\n]+|\n\s*\n)", re.MULTILINE)
    for match in pattern.finditer(text):
        candidates.append(match.end())
        if len(candidates) > chunk_size:
            break
    return sorted(set(candidates))


def _heading_path(text: str, position: int) -> str:
    headings: list[tuple[int, str]] = []
    for match in re.finditer(r"(?m)^(#{1,6})\s+(.+)$", text):
        if match.start() > position:
            break
        level = len(match.group(1))
        title = match.group(2).strip()
        while headings and headings[-1][0] >= level:
            headings.pop()
        headings.append((level, title))

    if headings:
        return " / ".join(title for _, title in headings)

    first_line = text[: min(len(text), position + 80)].splitlines()
    return first_line[0].strip()[:80] if first_line else ""
