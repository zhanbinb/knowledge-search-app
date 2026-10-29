from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"
    data_dir: Path = Path("./data")
    public_base_url: str = "http://127.0.0.1:8000"

    agent_model: str = "mimo-v2.6-flash"
    agent_temperature: float = 0.2
    agent_max_tokens: int = 1200
    openai_api_key: SecretStr = SecretStr("")
    openai_base_url: str = "https://token-plan-cn.xiaomimimo.com/v1"

    siliconflow_api_key: SecretStr = SecretStr("")
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"

    chunk_size: int = Field(default=800, ge=200, le=4000)
    chunk_overlap: int = Field(default=120, ge=0, le=1000)
    bm25_candidate_count: int = Field(default=20, ge=1, le=100)
    vector_candidate_count: int = Field(default=20, ge=1, le=100)
    rrf_k: int = Field(default=60, ge=1, le=1000)
    rerank_candidate_count: int = Field(default=20, ge=1, le=100)
    final_context_count: int = Field(default=5, ge=1, le=20)
    rerank_score_threshold: float = Field(default=0.15, ge=-1.0, le=1.0)

    model_timeout_seconds: float = Field(default=60, gt=0)
    model_max_retries: int = Field(default=3, ge=0, le=10)
    tool_timeout_seconds: float = Field(default=10, gt=0)
    max_tool_calls: int = Field(default=5, ge=1, le=20)
    max_upload_size_mb: int = Field(default=10, ge=1, le=100)

    mcp_enabled: bool = True
    mcp_server_command: str = "uv"
    mcp_server_args: str = "run,mcp_server/server.py"

    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4318/v1/traces"

    @field_validator("chunk_overlap")
    @classmethod
    def validate_overlap(cls, value: int, info) -> int:
        chunk_size = info.data.get("chunk_size", 800)
        if value >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return value

    @property
    def database_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def chroma_path(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def upload_path(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def mcp_command_args(self) -> list[str]:
        return [part.strip() for part in self.mcp_server_args.split(",") if part.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_path.mkdir(parents=True, exist_ok=True)

    def validate_model_configuration(self) -> list[str]:
        errors: list[str] = []
        if not self.openai_api_key.get_secret_value():
            errors.append("OPENAI_API_KEY is required")
        if not self.siliconflow_api_key.get_secret_value():
            errors.append("SILICONFLOW_API_KEY is required")
        if not self.openai_base_url.startswith(("http://", "https://")):
            errors.append("OPENAI_BASE_URL must be an HTTP(S) URL")
        if not self.siliconflow_base_url.startswith(("http://", "https://")):
            errors.append("SILICONFLOW_BASE_URL must be an HTTP(S) URL")
        return errors


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
