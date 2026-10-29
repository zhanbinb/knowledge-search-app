from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.errors import DocumentNotFoundError, InvalidRequestError, SessionNotFoundError
from app.models import ChatRequest

router = APIRouter(prefix="/api/v1")


def container(request: Request):
    return request.app.state.container


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    app = container(request)
    settings = app.settings
    return {
        "status": "ok",
        "components": {
            "database": "ok",
            "vector_store": "ok" if app.vector_store.count >= 0 else "error",
            "chat_model_configured": bool(settings.openai_api_key.get_secret_value()),
            "embedding_model_configured": bool(
                settings.siliconflow_api_key.get_secret_value()
            ),
            "rerank_model_configured": bool(settings.siliconflow_api_key.get_secret_value()),
            "mcp_server": "configured" if settings.mcp_enabled else "disabled",
        },
        "trace_id": request.state.trace_id,
    }


@router.get("/ready")
async def ready(request: Request) -> dict[str, Any]:
    app = container(request)
    config_errors = app.settings.validate_model_configuration()
    ready_state = not config_errors
    return {
        "ready": bool(ready_state),
        "configuration_errors": config_errors,
        "document_count": len(app.database.list_documents()),
        "chunk_count": app.bm25_index.count,
        "trace_id": request.state.trace_id,
    }


@router.post("/documents")
async def upload_document(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    app = container(request)
    content = await file.read()
    document = app.document_service.ingest(content, file.filename or "document.txt")
    return {"data": document, "trace_id": request.state.trace_id}


@router.get("/documents")
async def list_documents(request: Request) -> dict[str, Any]:
    app = container(request)
    return {
        "documents": app.database.list_documents(),
        "trace_id": request.state.trace_id,
    }


@router.get("/documents/{document_id}")
async def get_document(document_id: str, request: Request) -> dict[str, Any]:
    app = container(request)
    document = app.database.get_document(document_id)
    if not document:
        raise DocumentNotFoundError("文档不存在")
    return {"document": document, "trace_id": request.state.trace_id}


@router.post("/documents/{document_id}/reprocess")
async def reprocess_document(document_id: str, request: Request) -> dict[str, Any]:
    app = container(request)
    document = app.document_service.reprocess(document_id)
    return {"document": document, "trace_id": request.state.trace_id}


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str, request: Request) -> dict[str, Any]:
    app = container(request)
    app.document_service.delete(document_id)
    return {"deleted": True, "trace_id": request.state.trace_id}


@router.post("/indexes/rebuild")
async def rebuild_indexes(request: Request) -> dict[str, Any]:
    app = container(request)
    result = app.document_service.rebuild_indexes()
    return {"data": result, "trace_id": request.state.trace_id}


@router.post("/chat")
async def chat(payload: ChatRequest, request: Request) -> dict[str, Any]:
    app = container(request)
    result = await app.chat_service.answer(
        question=payload.question,
        session_id=payload.session_id,
        trace_id=request.state.trace_id,
    )
    return result


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    app = container(request)

    async def events():
        async for item in app.chat_service.stream(
            question=payload.question,
            session_id=payload.session_id,
            trace_id=request.state.trace_id,
        ):
            yield (
                f"event: {item['event']}\n"
                f"data: {json.dumps(item['data'], ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions")
async def list_sessions(request: Request) -> dict[str, Any]:
    app = container(request)
    return {"sessions": app.database.list_sessions(), "trace_id": request.state.trace_id}


@router.post("/sessions")
async def create_session(request: Request) -> dict[str, Any]:
    app = container(request)
    return {"session": app.database.create_session(), "trace_id": request.state.trace_id}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request) -> dict[str, Any]:
    app = container(request)
    session = app.database.get_session(session_id)
    if not session:
        raise SessionNotFoundError("会话不存在")
    return {
        "session": session,
        "messages": app.database.list_messages(session_id),
        "trace_id": request.state.trace_id,
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request) -> dict[str, Any]:
    app = container(request)
    app.database.delete_session(session_id)
    return {"deleted": True, "trace_id": request.state.trace_id}


@router.get("/tools")
async def list_tools(request: Request) -> dict[str, Any]:
    app = container(request)
    return {"tools": app.tool_registry.list_tools(), "trace_id": request.state.trace_id}


@router.post("/tools/{tool_name}/invoke")
async def invoke_tool(
    tool_name: str, payload: dict[str, Any], request: Request
) -> dict[str, Any]:
    app = container(request)
    arguments = payload.get("arguments")
    if arguments is not None and not isinstance(arguments, dict):
        raise InvalidRequestError("arguments 必须是对象")
    result = await app.tool_registry.call(tool_name, arguments or {})
    return {"result": result, "trace_id": request.state.trace_id}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request) -> dict[str, Any]:
    app = container(request)
    return {"run": app.database.get_run_details(run_id), "trace_id": request.state.trace_id}
