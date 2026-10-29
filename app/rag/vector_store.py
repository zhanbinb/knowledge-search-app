from __future__ import annotations

from typing import Any

import chromadb

from app.config import Settings
from app.rag.embeddings import EmbeddingClient


class VectorStore:
    def __init__(self, settings: Settings, embedding_client: EmbeddingClient) -> None:
        self.settings = settings
        self.embedding_client = embedding_client
        self._client = chromadb.PersistentClient(path=str(settings.chroma_path))
        self._collection = self._client.get_or_create_collection(
            name="knowledge_chunks",
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def count(self) -> int:
        return self._collection.count()

    def upsert_document(self, document_id: str, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            return
        self.delete_document(document_id)
        texts = [chunk["content"] for chunk in chunks]
        embeddings = self.embedding_client.embed_documents(texts)
        self._collection.upsert(
            ids=[chunk["id"] for chunk in chunks],
            embeddings=embeddings,
            documents=texts,
            metadatas=[
                {
                    "document_id": document_id,
                    "chunk_id": chunk["id"],
                    "filename": chunk["filename"],
                    "heading_path": chunk.get("heading_path", ""),
                    "page_number": chunk.get("page_number") or 0,
                    "chunk_index": chunk.get("chunk_index", 0),
                }
                for chunk in chunks
            ],
        )

    def delete_document(self, document_id: str) -> None:
        try:
            self._collection.delete(where={"document_id": document_id})
        except Exception:
            pass

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        if self.count == 0:
            return []
        query_embedding = self.embedding_client.embed_query(query)
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(limit, self.count),
            include=["documents", "metadatas", "distances"],
        )

        items: list[dict[str, Any]] = []
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        for index, chunk_id in enumerate(ids):
            distance = float(distances[index]) if index < len(distances) else 1.0
            metadata = metadatas[index] if index < len(metadatas) else {}
            items.append(
                {
                    "chunk_id": chunk_id,
                    "score": 1.0 / (1.0 + max(distance, 0.0)),
                    "content": documents[index],
                    "payload": metadata,
                }
            )
        return items
