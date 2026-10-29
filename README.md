# 知问 · 企业知识 Agent Demo

基于 Python、LangChain、LangGraph、RAG、MCP 和 FastAPI 的企业知识库问答 Demo。

## 功能

- PDF、Markdown、TXT 文档解析与切分。
- BM25 + Chroma 向量双召回、RRF 融合和 BGE Reranker。
- LangGraph 知识、工具、混合和澄清条件路由。
- 普通工具与本地 MCP 工具调用。
- 多轮会话、引用来源和运行追踪。
- FastAPI JSON API、SSE 接口和静态 Web UI。

## 快速启动

```bash
uv python install 3.11
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

## 配置

复制 `.env.example` 为 `.env`，配置：

- MiMo Chat API。
- 硅基流动 `BAAI/bge-m3` Embedding API。
- 硅基流动 `BAAI/bge-reranker-v2-m3` Rerank API。

`.env` 已被 `.gitignore` 忽略，不要提交真实 API Key。

## 导入样例知识库

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents \
  -F "file=@sample_docs/employee-travel-policy.md"
```

重复上传同一文件会根据 SHA-256 摘要返回已有文档。

## 问答

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"深圳出差住宿每晚最多报销多少？"}'
```

## 测试

```bash
uv run pytest
```

真实模型连通性测试：

```bash
uv run python scripts/smoke_models.py
```

## 主要接口

- `GET /health`
- `GET /ready`
- `POST /api/v1/documents`
- `GET /api/v1/documents`
- `POST /api/v1/chat`
- `POST /api/v1/chat/stream`
- `GET /api/v1/sessions`
- `GET /api/v1/tools`
- `GET /api/v1/runs/{run_id}`

完整设计见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。
