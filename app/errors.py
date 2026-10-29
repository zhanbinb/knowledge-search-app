from __future__ import annotations

from typing import Any


class AppError(Exception):
    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(self, message: str, *, detail: Any | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class InvalidRequestError(AppError):
    code = "INVALID_REQUEST"
    status_code = 400


class DocumentNotFoundError(AppError):
    code = "DOCUMENT_NOT_FOUND"
    status_code = 404


class SessionNotFoundError(AppError):
    code = "SESSION_NOT_FOUND"
    status_code = 404


class DocumentNotReadyError(AppError):
    code = "DOCUMENT_NOT_READY"
    status_code = 409


class FileTooLargeError(AppError):
    code = "FILE_TOO_LARGE"
    status_code = 413


class UnsupportedFileTypeError(AppError):
    code = "UNSUPPORTED_FILE_TYPE"
    status_code = 422


class UpstreamRateLimitedError(AppError):
    code = "UPSTREAM_RATE_LIMITED"
    status_code = 429


class ServiceNotConfiguredError(AppError):
    code = "SERVICE_NOT_CONFIGURED"
    status_code = 503


class RAGNotReadyError(AppError):
    code = "RAG_NOT_READY"
    status_code = 503


class UpstreamModelError(AppError):
    code = "UPSTREAM_MODEL_ERROR"
    status_code = 502


def walk_exception_chain(error: BaseException, max_depth: int = 12) -> list[BaseException]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = error

    while current is not None and len(chain) < max_depth:
        identity = id(current)
        if identity in seen:
            break
        seen.add(identity)
        chain.append(current)
        current = current.__cause__ or current.__context__

    return chain


def classify_exception(error: BaseException) -> AppError:
    for item in walk_exception_chain(error):
        if isinstance(item, AppError):
            return item

        name = item.__class__.__name__.lower()
        text = str(item).lower()

        if "ratelimit" in name or "rate limit" in text or "429" in text:
            return UpstreamRateLimitedError("模型服务触发限流")
        if "timeout" in name or "timed out" in text:
            return UpstreamModelError("模型或工具服务调用超时")
        if "authentication" in name or "unauthorized" in text or "invalid api key" in text:
            return ServiceNotConfiguredError("模型服务认证失败，请检查 API 配置")
        if "connection" in name or "connection error" in text:
            return UpstreamModelError("无法连接模型或工具服务")

    return AppError("服务内部错误")
