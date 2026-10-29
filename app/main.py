from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import health as health_endpoint
from app.api.routes import ready as ready_endpoint
from app.api.routes import router
from app.config import get_settings
from app.container import ApplicationContainer
from app.errors import AppError, InvalidRequestError, classify_exception
from app.observability.logging import (
    configure_logging,
    get_trace_id,
    new_trace_id,
    set_trace_id,
)

logger = logging.getLogger(__name__)
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def configure_otel(app: FastAPI, endpoint: str) -> None:
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(
            resource=Resource.create({"service.name": "knowledge-search-app"})
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        logger.warning("OpenTelemetry initialization failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    container = ApplicationContainer.create(settings)
    app.state.container = container
    if settings.otel_enabled:
        configure_otel(app, settings.otel_exporter_otlp_endpoint)
    logger.info("application started", extra={"component": "startup"})
    yield
    container.close()
    logger.info("application stopped", extra={"component": "shutdown"})


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="知问 · 企业知识 Agent",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        trace_id = request.headers.get("X-Trace-ID") or new_trace_id()
        set_trace_id(trace_id)
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {"code": exc.code, "message": exc.message},
                "trace_id": getattr(request.state, "trace_id", get_trace_id()),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "请求参数不合法",
                    "detail": exc.errors(),
                },
                "trace_id": getattr(request.state, "trace_id", get_trace_id()),
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        error = classify_exception(exc)
        logger.exception("unhandled request error")
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {"code": error.code, "message": error.message},
                "trace_id": getattr(request.state, "trace_id", get_trace_id()),
            },
        )

    app.include_router(router)

    @app.get("/health", include_in_schema=False)
    async def root_health(request: Request):
        return await health_endpoint(request)

    @app.get("/ready", include_in_schema=False)
    async def root_ready(request: Request):
        return await ready_endpoint(request)

    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(WEB_DIR / "index.html")

    return app


app = create_app()
