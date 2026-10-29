from __future__ import annotations

from typing import Any

from app.config import Settings
from app.errors import RAGNotReadyError
from app.rag.bm25 import BM25Index
from app.rag.embeddings import EmbeddingClient, RerankClient
from app.rag.fusion import reciprocal_rank_fusion
from app.rag.vector_store import VectorStore


class HybridRetriever:
    def __init__(
        self,
        settings: Settings,
        embedding_client: EmbeddingClient,
        rerank_client: RerankClient,
        vector_store: VectorStore,
        bm25_index: BM25Index,
    ) -> None:
        self.settings = settings
        self.embedding_client = embedding_client
        self.rerank_client = rerank_client
        self.vector_store = vector_store
        self.bm25_index = bm25_index

    @property
    def ready(self) -> bool:
        return self.bm25_index.count > 0 and self.vector_store.count > 0

    def rebuild_index(self, chunks: list[dict[str, Any]]) -> None:
        self.bm25_index.rebuild(chunks)

    def search(self, query: str) -> dict[str, Any]:
        if not self.ready:
            raise RAGNotReadyError("知识库尚未建立可用索引")

        bm25_results = self.bm25_index.search(query, self.settings.bm25_candidate_count)
        vector_results = self.vector_store.search(query, self.settings.vector_candidate_count)
        fused = reciprocal_rank_fusion(
            [bm25_results, vector_results],
            k=self.settings.rrf_k,
        )[: self.settings.rerank_candidate_count]

        if not fused:
            return {
                "bm25": [],
                "vector": [],
                "fused": [],
                "reranked": [],
                "rerank_fallback": True,
            }

        try:
            rerank_results = self.rerank_client.rerank(
                query,
                [item["content"] for item in fused],
                self.settings.final_context_count,
            )
            reranked: list[dict[str, Any]] = []
            for result in rerank_results:
                index = int(result["index"])
                if index >= len(fused):
                    continue
                item = dict(fused[index])
                item["rerank_score"] = float(result["score"])
                item["content"] = result.get("document", item["content"])
                reranked.append(item)
            rerank_fallback = False
        except Exception:
            reranked = [
                {**item, "rerank_score": None} for item in fused[: self.settings.final_context_count]
            ]
            rerank_fallback = True

        return {
            "bm25": bm25_results,
            "vector": vector_results,
            "fused": fused,
            "reranked": reranked,
            "rerank_fallback": rerank_fallback,
        }
