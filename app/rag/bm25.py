from __future__ import annotations

import re
from typing import Any

import jieba
from rank_bm25 import BM25Okapi


class BM25Index:
    def __init__(self) -> None:
        self._bm25: BM25Okapi | None = None
        self._chunks: list[dict[str, Any]] = []

    @property
    def count(self) -> int:
        return len(self._chunks)

    def rebuild(self, chunks: list[dict[str, Any]]) -> None:
        self._chunks = chunks
        tokenized = [self._tokenize(self._search_text(item)) for item in chunks]
        self._bm25 = BM25Okapi(tokenized) if tokenized else None

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        if not self._bm25 or not self._chunks:
            return []
        scores = self._bm25.get_scores(self._tokenize(query))
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)[:limit]
        results: list[dict[str, Any]] = []
        for index, score in ranked:
            if score <= 0:
                continue
            chunk = self._chunks[index]
            results.append(
                {
                    "chunk_id": chunk["id"],
                    "score": float(score),
                    "content": chunk["content"],
                    "payload": {
                        "document_id": chunk["document_id"],
                        "chunk_id": chunk["id"],
                        "filename": chunk["filename"],
                        "heading_path": chunk.get("heading_path", ""),
                        "page_number": chunk.get("page_number") or 0,
                        "chunk_index": chunk.get("chunk_index", 0),
                    },
                }
            )
        return results

    @staticmethod
    def _search_text(item: dict[str, Any]) -> str:
        return f"{item.get('heading_path', '')}\n{item.get('content', '')}\n{item.get('filename', '')}"

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        text = text.lower()
        tokens = jieba.lcut_for_search(text)
        return [re.sub(r"\s+", "", token) for token in tokens if token.strip()]
