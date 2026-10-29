from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RouteDecision(BaseModel):
    route: Literal["knowledge", "tool", "hybrid", "clarify"]
    confidence: float = Field(default=0.5, ge=0, le=1)
    reason: str = ""


class ToolPlan(BaseModel):
    tool_name: Literal[
        "get_current_time",
        "calculator",
        "lookup_policy",
        "calculate_business_days",
        "none",
    ]
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class DocumentResponse(BaseModel):
    document_id: str
    filename: str
    file_type: str
    status: str
    chunk_count: int
    char_count: int
    error_message: str | None = None
    created_at: str
    updated_at: str


class Citation(BaseModel):
    index: int
    document_id: str
    chunk_id: str
    filename: str
    heading_path: str = ""
    page_number: int | None = None
    snippet: str
    rerank_score: float | None = None


class ToolCallResponse(BaseModel):
    id: str
    tool_name: str
    tool_source: Literal["langchain", "mcp", "fallback"]
    arguments: dict[str, Any]
    result_summary: str
    status: str
    latency_ms: int


class ChatRequest(BaseModel):
    session_id: str | None = None
    question: str = Field(min_length=1, max_length=4000)
    stream: bool = False


class ChatResponse(BaseModel):
    session_id: str
    run_id: str
    answer: str
    route: str
    citations: list[Citation] = Field(default_factory=list)
    tool_calls: list[ToolCallResponse] = Field(default_factory=list)
    trace_id: str
    latency_ms: int


class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class ErrorResponse(BaseModel):
    error: dict[str, Any]
    trace_id: str
