from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from typing import Any, AsyncIterator

from app.agents.graph import KnowledgeAgentGraph
from app.config import Settings
from app.db.database import Database
from app.errors import SessionNotFoundError, classify_exception
from app.models import Citation

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        agent: KnowledgeAgentGraph,
    ) -> None:
        self.settings = settings
        self.database = database
        self.agent = agent

    async def answer(
        self,
        *,
        question: str,
        session_id: str | None,
        trace_id: str,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        session = self._resolve_session(session_id, question)
        messages = self.database.list_messages(session["id"])
        run_id = f"run_{uuid.uuid4().hex}"
        self.database.create_run(
            run_id=run_id, trace_id=trace_id, session_id=session["id"]
        )

        try:
            result = await self.agent.run(
                {
                    "session_id": session["id"],
                    "run_id": run_id,
                    "trace_id": trace_id,
                    "question": question,
                    "messages": messages,
                }
            )
            citations = self._build_citations(result)
            tool_calls = self._persist_tool_calls(run_id, result.get("tool_results", []))
            self._persist_retrieval_logs(run_id, result.get("retrieved", {}))

            answer = result.get("answer", "")
            if not result.get("reranked"):
                answer = re.sub(r"\[\d+\]", "", answer)
            self.database.add_message(session["id"], "user", question)
            self.database.add_message(session["id"], "assistant", answer)

            latency_ms = int((time.perf_counter() - started) * 1000)
            self.database.update_run(
                run_id,
                route=result.get("route", "knowledge"),
                status="SUCCEEDED",
                latency_ms=latency_ms,
                route_reason=result.get("route_reason", ""),
            )

            return {
                "session_id": session["id"],
                "run_id": run_id,
                "answer": answer,
                "route": result.get("route", "knowledge"),
                "citations": citations,
                "tool_calls": tool_calls,
                "trace_id": trace_id,
                "latency_ms": latency_ms,
            }
        except Exception as exc:
            app_error = classify_exception(exc)
            latency_ms = int((time.perf_counter() - started) * 1000)
            self.database.update_run(
                run_id,
                route="unknown",
                status="FAILED",
                latency_ms=latency_ms,
                error_code=app_error.code,
            )
            logger.exception(
                "chat execution failed",
                extra={
                    "run_id": run_id,
                    "session_id": session["id"],
                    "error_code": app_error.code,
                },
            )
            raise app_error from exc

    async def stream(
        self,
        *,
        question: str,
        session_id: str | None,
        trace_id: str,
    ) -> AsyncIterator[dict[str, Any]]:
        yield {"event": "start", "data": {"trace_id": trace_id}}
        try:
            result = await asyncio.wait_for(
                self.answer(question=question, session_id=session_id, trace_id=trace_id),
                timeout=self.settings.model_timeout_seconds + 15,
            )
            yield {"event": "route", "data": {"route": result["route"]}}
            if result["citations"]:
                yield {"event": "retrieval", "data": {"count": len(result["citations"])}}
            for tool_call in result["tool_calls"]:
                yield {"event": "tool", "data": tool_call}

            answer = result["answer"]
            step = max(4, len(answer) // 30)
            for start in range(0, len(answer), step):
                yield {"event": "token", "data": {"content": answer[start : start + step]}}

            for citation in result["citations"]:
                yield {"event": "citation", "data": citation}
            yield {"event": "done", "data": result}
        except Exception as exc:
            error = classify_exception(exc)
            yield {
                "event": "error",
                "data": {"code": error.code, "message": error.message},
            }

    def _resolve_session(self, session_id: str | None, question: str) -> dict[str, Any]:
        if session_id:
            session = self.database.get_session(session_id)
            if not session:
                raise SessionNotFoundError("会话不存在")
            return session
        title = question.strip().replace("\n", " ")[:28] or "新对话"
        return self.database.create_session(title=title)

    @staticmethod
    def _build_citations(result: dict[str, Any]) -> list[Citation]:
        contexts = result.get("reranked", [])
        answer = result.get("answer", "")
        referenced = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
        indices = sorted(index for index in referenced if 1 <= index <= len(contexts))
        if not indices and contexts:
            indices = [1]

        citations: list[Citation] = []
        for context_index in indices:
            item = contexts[context_index - 1]
            payload = item.get("payload", {})
            snippet = item.get("content", "")
            citations.append(
                Citation(
                    index=context_index,
                    document_id=payload.get("document_id", ""),
                    chunk_id=item.get("chunk_id", payload.get("chunk_id", "")),
                    filename=payload.get("filename", "未知文档"),
                    heading_path=payload.get("heading_path", ""),
                    page_number=payload.get("page_number") or None,
                    snippet=snippet[:500],
                    rerank_score=item.get("rerank_score"),
                )
            )
        return citations

    def _persist_tool_calls(
        self, run_id: str, tool_results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        persisted: list[dict[str, Any]] = []
        for item in tool_results:
            call_id = self.database.add_tool_call(
                run_id=run_id,
                tool_name=item["tool_name"],
                tool_source=item["tool_source"],
                arguments=item.get("arguments", {}),
                result_summary=item.get("result_summary", ""),
                status=item["status"],
                latency_ms=item.get("latency_ms", 0),
            )
            persisted.append({**item, "id": call_id})
        return persisted

    def _persist_retrieval_logs(self, run_id: str, retrieved: dict[str, Any]) -> None:
        for stage in ("bm25", "vector", "fused", "reranked"):
            items = []
            for item in retrieved.get(stage, []):
                items.append(
                    {
                        "chunk_id": item.get("chunk_id", ""),
                        "score": item.get("rerank_score", item.get("score", 0)),
                        "payload": item.get("payload", {}),
                    }
                )
            self.database.add_retrieval_logs(run_id, stage, items)
