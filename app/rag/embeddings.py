from __future__ import annotations

from typing import Any

import httpx
from langchain_openai import OpenAIEmbeddings

from app.config import Settings
from app.errors import UpstreamModelError, UpstreamRateLimitedError


class EmbeddingClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=settings.siliconflow_api_key.get_secret_value(),
            base_url=settings.siliconflow_base_url,
            timeout=settings.model_timeout_seconds,
            max_retries=settings.model_max_retries,
        )

    @property
    def model(self) -> str:
        return self.settings.embedding_model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._client.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed_query(text)


class RerankClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def model(self) -> str:
        return self.settings.rerank_model

    def rerank(self, query: str, documents: list[str], top_n: int) -> list[dict[str, Any]]:
        if not documents:
            return []

        payload = {
            "model": self.settings.rerank_model,
            "query": query,
            "documents": documents,
            "top_n": min(top_n, len(documents)),
            "return_documents": True,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.siliconflow_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

        try:
            response = httpx.post(
                f"{self.settings.siliconflow_base_url.rstrip('/')}/rerank",
                json=payload,
                headers=headers,
                timeout=self.settings.model_timeout_seconds,
            )
            if response.status_code == 429:
                raise UpstreamRateLimitedError("Rerank 服务触发限流")
            if response.status_code >= 400:
                raise UpstreamModelError(f"Rerank 服务返回 {response.status_code}")
            body = response.json()
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise UpstreamModelError("Rerank 服务调用失败") from exc

        results = body.get("results", [])
        normalized: list[dict[str, Any]] = []
        for result in results:
            index = int(result.get("index", 0))
            normalized.append(
                {
                    "index": index,
                    "score": float(result.get("relevance_score", result.get("score", 0))),
                    "document": result.get("document", {}).get("text", documents[index])
                    if isinstance(result.get("document"), dict)
                    else result.get("document", documents[index]),
                }
            )
        return normalized
