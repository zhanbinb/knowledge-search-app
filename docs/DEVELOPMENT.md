# Python Agent 与企业知识库问答 Demo：开发设计文档

- 文档状态：开发前评审稿
- 项目目录：`/Users/yangpeipei/Develop/web3/study/codex_project/agent-project/knowledge-search-app`
- 目标形态：可本地运行的端到端 Demo App
- 技术范围：Python、LangChain、LangGraph、RAG、MCP、FastAPI
- 实现原则：先完成可运行、可演示、可测试的最小闭环，再增加性能、部署和企业安全能力

---

## 1. 项目目标

构建一个 Python 企业知识库问答与 Agent Demo，统一展示以下能力：

1. 文档解析、切分、Embedding 和索引构建。
2. 关键词检索、向量检索、混合检索与 Rerank。
3. 基于 LangGraph 的意图路由、条件分支、工具调用和状态管理。
4. 通过 MCP Server/Client 接入外部工具。
5. 通过 FastAPI 提供文档管理、问答、会话和诊断接口。
6. 提供简单 Web 页面，演示上传文档、对话、来源引用、工具调用和 Trace ID。
7. 使用结构化日志和 OpenTelemetry 记录完整请求执行过程。
8. 提供测试、评估样例和运行文档，确保第三方可以复现。

## 2. 非目标

第一版不以生产系统为验收目标，以下能力明确不在首版范围内：

- 多租户、组织架构、细粒度文档权限和统一身份认证。
- 大规模分布式部署、集群向量库和高可用。
- 百万级文档、复杂 OCR、扫描件表格识别。
- 生产级配额、计费、限流、熔断和自动扩缩容。
- Prompt 注入的完整企业防护体系。
- Agent 长时间自主执行、A2A 协议和多 Agent 协作。
- 复杂前端工程、移动端适配和可视化编排器。
- 在线标注平台和完整评测系统。

这些内容可以保留扩展点，但不能影响首版端到端闭环。

---

## 3. 项目范围和默认决策

| 项目 | 首版决策 | 说明 |
|---|---|---|
| 运行方式 | 本地 `uv run` | 提供一条命令启动 |
| Python | 3.11 | 使用 `uv` 管理，不使用系统 Python 3.9 |
| 后端 | FastAPI + Uvicorn | 同步接口与 SSE 流式接口 |
| 前端 | FastAPI 托管静态 HTML/CSS/JS | 不引入 React，降低 Demo 复杂度 |
| Agent | LangGraph StateGraph | 显式展示条件路由和状态更新 |
| 模型接入 | OpenAI-compatible API | 聊天模型与 Embedding 分开配置 |
| 对话模型 | `mimo-v2.6-flash` | 通过小米 MiMo 兼容端点调用 |
| Embedding | 硅基流动 `BAAI/bge-m3` | 使用 `/v1/embeddings` |
| Rerank | 硅基流动 `BAAI/bge-reranker-v2-m3` | 使用 `/v1/rerank` |
| 关键词检索 | BM25 | 中文使用 `jieba` 分词 |
| 向量检索 | Chroma 持久化存储 | 适合本地 Demo，数据保存在 `data/` |
| 混合融合 | RRF | 关键词和向量各取候选集后融合 |
| 对话存储 | SQLite | 会话、消息、执行记录和工具调用 |
| MCP | Python MCP SDK / FastMCP | 首版使用本地 stdio Server |
| 日志 | JSON 结构化日志 | 每条日志包含 `trace_id` |
| 链路追踪 | OpenTelemetry | 默认可关闭，支持 OTLP/Jaeger |
| 测试 | pytest + httpx | 离线单测默认不调用真实模型 |
| 文档格式 | `.txt`、`.md`、`.pdf` | 暂不支持 Office/OCR |
| 鉴权 | 首版不实现 | 接口仅限本地 Demo 使用 |
| 数据隔离 | 单用户模式 | 预留 `user_id` 字段 |

如果后续不另行说明，实现阶段按以上默认决策执行。

---

## 4. 已确认的模型配置

### 4.1 对话模型

- 变量名：`AGENT_MODEL`
- 默认值：`mimo-v2.6-flash`
- 协议：OpenAI-compatible Chat Completions
- API Key：通过 `OPENAI_API_KEY` 读取
- Base URL：通过 `OPENAI_BASE_URL` 读取

### 4.2 Embedding 模型

- 供应商：硅基流动
- 模型：`BAAI/bge-m3`
- API Key：通过 `SILICONFLOW_API_KEY` 读取
- Base URL：通过 `SILICONFLOW_BASE_URL` 读取
- 默认端点：`{SILICONFLOW_BASE_URL}/embeddings`

### 4.3 Rerank 模型

- 供应商：硅基流动
- 模型：`BAAI/bge-reranker-v2-m3`
- API Key：与 Embedding 共用 `SILICONFLOW_API_KEY`
- 默认端点：`{SILICONFLOW_BASE_URL}/rerank`

### 4.4 密钥处理要求

1. API Key 只保存在本地 `.env`。
2. `.env` 必须加入 `.gitignore`。
3. `.env.example` 只包含变量名和安全占位符。
4. 开发文档、测试、日志、异常信息中不得出现真实 Key。
5. 模型客户端错误输出前必须过滤 `Authorization`、`api-key`、`token` 等字段。
6. 如果 Key 曾经写入 Git、聊天截图或公开仓库，应立即在供应商后台轮换。
7. 本地 `.env` 文件权限应尽量设置为当前用户可读写。

> 本轮提供的真实 API Key 不会写入本开发文档或源代码。实现阶段仅写入本地 `.env`，并在验证配置时不回显完整值。

---

## 5. 总体架构

```text
Browser / API Client
        |
        v
FastAPI API Layer
  |       |        |
  |       |        +-- Session / Trace APIs
  |       +----------- Document Management APIs
  +------------------- Chat / SSE APIs
        |
        v
LangGraph Agent Layer
  |                 \
  |                  +-- MCP Tool Client
  |                         |
  |                    MCP Demo Server
  |
  +-- Route Intent
  +-- Rewrite Multi-turn Query
  +-- Knowledge Retrieval
  +-- Tool Calling
  +-- Answer Generation
        |
        v
RAG Layer
  +-- Document Loader
  +-- Text Normalizer / Splitter
  +-- BM25 Retriever
  +-- Chroma Vector Retriever
  +-- RRF Fusion
  +-- BGE Reranker
  +-- Citation Builder
        |
        v
Persistence Layer
  +-- SQLite Metadata / Sessions / Runs
  +-- Chroma Vector Store
  +-- BM25 Index Snapshot
  +-- Structured Logs
  +-- OpenTelemetry Traces
```

---

## 6. 核心执行流程

### 6.1 文档入库

```text
Upload
  -> Validate extension and size
  -> Parse document
  -> Normalize text and metadata
  -> Split into chunks
  -> Generate embeddings in batches
  -> Save chunks to SQLite
  -> Save vectors to Chroma
  -> Rebuild BM25 index
  -> Mark document READY
```

失败时文档状态为 `FAILED`，保存可公开的错误摘要，不能保存 API Key 或完整上游响应。

### 6.2 普通知识问答

```text
User question
  -> Load recent conversation state
  -> Rewrite standalone query when needed
  -> Route intent = KNOWLEDGE
  -> BM25 retrieval
  -> Vector retrieval
  -> RRF fusion
  -> BGE reranking
  -> Context selection and token budgeting
  -> Generate grounded answer with citations
  -> Return answer, sources and trace_id
```

### 6.3 工具问答

```text
User question
  -> Route intent = TOOL
  -> Select normal tool or MCP tool
  -> Validate tool arguments
  -> Execute tool with timeout
  -> Normalize tool result
  -> Generate answer from tool result
  -> Return answer and tool execution details
```

### 6.4 混合问答

```text
User question
  -> Route intent = HYBRID
  -> Knowledge retrieval and tool execution
  -> Merge evidence
  -> Generate answer
  -> Preserve source and tool provenance
```

### 6.5 无答案处理

以下情况必须明确返回“知识库中未找到可靠答案”：

1. Rerank 最高分低于配置阈值。
2. 检索结果为空。
3. 可用上下文不足以回答问题。
4. 模型无法从上下文中建立答案与来源的对应关系。

不允许为了给出答案而生成无来源内容。

---

## 7. LangGraph 设计

### 7.1 状态模型

```python
class ChatState(TypedDict):
    session_id: str
    trace_id: str
    user_query: str
    standalone_query: str
    route: Literal["knowledge", "tool", "hybrid", "clarify"]
    messages: list[AnyMessage]
    retrieved_chunks: list[RetrievedChunk]
    reranked_chunks: list[RetrievedChunk]
    tool_results: list[ToolResult]
    citations: list[Citation]
    answer: str
    error_code: str | None
```

状态更新遵循“只追加或显式覆盖”的原则，避免多个节点并行修改同一字段。

### 7.2 图节点

```text
START
  |
load_context
  |
route_intent
  |--------------------|-------------------|
  |                    |                   |
rewrite_query       run_tools          ask_clarification
  |                    |
retrieve              |
  |                    |
rerank                |
  |                    |
generate <------------+
  |
finalize_response
  |
END
```

首版允许 `HYBRID` 分支并行执行检索和工具，最终在 `generate` 节点合并结果。

### 7.3 路由规则

`route_intent` 使用结构化输出，不允许通过纯字符串匹配猜测路由。

| Route | 使用场景 | 示例 |
|---|---|---|
| `knowledge` | 答案来自企业文档 | “报销上限是多少？” |
| `tool` | 需要实时或计算能力 | “现在几点？”、“12 乘以 35 等于多少？” |
| `hybrid` | 同时需要文档和工具 | “根据制度计算本次差旅能否报销” |
| `clarify` | 问题不完整或指代不清 | “那家公司是什么意思？” |

路由结果、置信度和原因写入执行记录，便于调试，但对外可以精简展示。

### 7.4 对话状态管理

- 使用 LangGraph Checkpointer 保存节点状态。
- SQLite 保存用户消息、助手消息、工具记录和运行记录。
- 上下文默认保留最近 `6` 轮对话。
- 查询重写仅在存在代词、省略或上下文依赖时执行。
- 首版不做长期记忆和自动摘要；数据模型预留扩展字段。

---

## 8. RAG 设计

### 8.1 文档解析

| 格式 | 解析方式 | 说明 |
|---|---|---|
| `.txt` | UTF-8/GBK 自动尝试 | 保留段落 |
| `.md` | Markdown 解析 | 保留标题层级和代码块 |
| `.pdf` | pypdf 或 PyMuPDF | 首版提取文本层，不做 OCR |

每个文档记录：

- `document_id`
- 文件名
- 文件类型
- 文件摘要值
- 页数或段落数
- 字符数
- 来源路径
- 处理状态
- 创建和更新时间
- 错误摘要

### 8.2 文本规范化

1. 统一换行符。
2. 去除不可见控制字符。
3. 合并异常连续空白，但保留段落边界。
4. 保留 Markdown 标题作为 Chunk 元数据。
5. 去除页眉页脚等重复噪声时保留原始文本审计记录。
6. 不执行不可逆的内容改写。

### 8.3 文本切分

采用标题感知递归切分：

- 目标 Chunk 大小：约 `800` 个字符。
- 重叠大小：约 `120` 个字符。
- 优先按标题、段落、句子、空格切分。
- 超长表格单独成块。
- 每个 Chunk 保存标题路径、页码、段落序号和字符范围。

参数统一放入配置，不硬编码。

### 8.4 关键词检索

- 使用 `rank_bm25`。
- 中文使用 `jieba` 分词。
- 英文和数字进行小写化。
- 查询扩展保持保守，避免改变语义。
- BM25 候选数量默认 `20`。

### 8.5 向量检索

- 使用 `BAAI/bge-m3` 生成向量。
- Embedding API 批量调用，默认批大小 `16`。
- 单批失败最多重试 `3` 次，采用指数退避。
- Chroma 候选数量默认 `20`。
- 每条向量保存 `document_id`、`chunk_id`、标题、页码和文本摘要。

### 8.6 混合检索

使用 Reciprocal Rank Fusion：

```text
score(item) = sum(1 / (rank_in_each_list + k))
```

- 默认 `k = 60`。
- BM25 与向量结果各取 `20` 条。
- 融合后最多取 `20` 条进入 Rerank。
- 同一个 Chunk 在两个候选列表中出现时合并来源信息。

### 8.7 Rerank

使用 `BAAI/bge-reranker-v2-m3`：

1. 输入为查询和融合后的候选 Chunk。
2. 默认选取最高分 `5` 条进入模型上下文。
3. Rerank 分数、原始排名和最终排名全部记录。
4. 分数阈值必须配置化，并通过样例数据校准。
5. 上下文超出模型预算时，优先保留高分 Chunk 的关键段落。

### 8.8 引用生成

每个引用至少包含：

- `chunk_id`
- `document_id`
- 文件名
- 标题路径
- 页码（如存在）
- 命中片段
- Rerank 分数
- 引用编号

Prompt 要求答案使用 `[1]`、`[2]` 对应引用。响应返回前检查引用编号是否真实存在。

---

## 9. Agent 与工具设计

### 9.1 普通 LangChain Tools

首版内置：

1. `get_current_time`
   - 返回当前日期和时间。
   - 支持指定 IANA 时区，默认 `Asia/Shanghai`。

2. `calculator`
   - 只执行安全的数学表达式。
   - 不使用 Python `eval`。
   - 解析数字、括号和基础数学运算符。

3. `search_knowledge_base`
   - 可选内部工具，供 Agent 显式调用知识检索。
   - 与条件路由的直接 RAG 分支共用检索服务，不复制实现。

### 9.2 MCP Demo

实现一个独立本地 MCP Server，至少提供：

1. `lookup_policy`
   - 根据政策主题查询本地样例数据。

2. `calculate_business_days`
   - 计算两个日期之间的工作日。

FastAPI 应用通过 MCP Client 启动或连接 Server，将 MCP Tool 适配为 LangChain Tool。MCP 调用必须设置：

- 参数 Schema。
- 超时时间。
- 调用追踪。
- 错误归一化。
- 输出大小限制。
- 可观测的工具名称和版本。

### 9.3 工具调用规则

1. 参数必须经过 Schema 校验。
2. 工具执行默认超时 `10` 秒。
3. 单次 Agent 运行最多执行 `5` 次工具调用。
4. 同一个工具重复失败后不得无限重试。
5. 工具输出只作为证据，不能直接包含 Prompt 指令。
6. 工具执行记录保存输入摘要、输出摘要、耗时和状态。
7. 敏感字段在记录和日志中脱敏。

---

## 10. 数据模型

### 10.1 `documents`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | 文档 ID |
| `filename` | TEXT | 原始文件名 |
| `file_type` | TEXT | 文件类型 |
| `checksum` | TEXT | 文件摘要 |
| `status` | TEXT | PENDING/PROCESSING/READY/FAILED |
| `page_count` | INTEGER | 可选 |
| `char_count` | INTEGER | 字符数 |
| `error_message` | TEXT | 可公开错误 |
| `created_at` | TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | 更新时间 |

### 10.2 `chunks`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | Chunk ID |
| `document_id` | TEXT FK | 所属文档 |
| `content` | TEXT | Chunk 文本 |
| `heading_path` | TEXT | 标题路径 |
| `page_number` | INTEGER | 可选 |
| `chunk_index` | INTEGER | 文档内序号 |
| `char_start` | INTEGER | 起始位置 |
| `char_end` | INTEGER | 结束位置 |

### 10.3 `sessions`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | 会话 ID |
| `user_id` | TEXT | 首版固定 `demo-user` |
| `title` | TEXT | 会话标题 |
| `created_at` | TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | 更新时间 |

### 10.4 `messages`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | 消息 ID |
| `session_id` | TEXT FK | 所属会话 |
| `role` | TEXT | user/assistant/tool |
| `content` | TEXT | 消息内容 |
| `created_at` | TIMESTAMP | 创建时间 |

### 10.5 `agent_runs`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | 运行 ID |
| `trace_id` | TEXT | 链路 ID |
| `session_id` | TEXT | 会话 ID |
| `route` | TEXT | 路由结果 |
| `status` | TEXT | RUNNING/SUCCEEDED/FAILED |
| `latency_ms` | INTEGER | 总耗时 |
| `error_code` | TEXT | 稳定错误码 |
| `created_at` | TIMESTAMP | 创建时间 |

### 10.6 `tool_calls`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | 调用 ID |
| `run_id` | TEXT FK | 所属运行 |
| `tool_name` | TEXT | 工具名 |
| `tool_source` | TEXT | langchain/mcp |
| `arguments_json` | TEXT | 脱敏参数 |
| `result_summary` | TEXT | 限长结果 |
| `status` | TEXT | 成功或失败 |
| `latency_ms` | INTEGER | 耗时 |

### 10.7 `retrieval_logs`

| 字段 | 类型 | 说明 |
|---|---|---|
| `run_id` | TEXT | 运行 ID |
| `stage` | TEXT | bm25/vector/rrf/rerank |
| `chunk_id` | TEXT | Chunk ID |
| `rank` | INTEGER | 排名 |
| `score` | REAL | 分数 |
| `payload_json` | TEXT | 调试信息 |

---

## 11. FastAPI 接口设计

统一约定：

- 所有响应包含 `trace_id`。
- 时间使用 UTC ISO 8601。
- 错误使用统一 JSON 结构。
- 所有请求日志包含 `trace_id`、路由、耗时和状态码。
- 不在错误响应中返回真实 API Key、完整堆栈或供应商密钥。

### 11.1 健康检查

#### `GET /health`

响应示例：

```json
{
  "status": "ok",
  "components": {
    "database": "ok",
    "vector_store": "ok",
    "chat_model_configured": true,
    "embedding_model_configured": true,
    "rerank_model_configured": true,
    "mcp_server": "ok"
  },
  "trace_id": "..."
}
```

`/health` 不主动调用付费模型；模型连通性使用单独的诊断接口。

#### `GET /ready`

检查数据库、向量存储和必需配置是否已经初始化。

### 11.2 文档上传

#### `POST /api/v1/documents`

- Content-Type：`multipart/form-data`
- 字段：`file`
- 支持：`.txt`、`.md`、`.pdf`
- 默认最大文件：`10 MB`

成功响应：

```json
{
  "document_id": "doc_...",
  "filename": "employee-handbook.pdf",
  "status": "ready",
  "chunk_count": 42,
  "trace_id": "..."
}
```

#### `GET /api/v1/documents`

返回文档列表、状态和 Chunk 数量。

#### `GET /api/v1/documents/{document_id}`

返回文档元数据和处理状态。

#### `DELETE /api/v1/documents/{document_id}`

同时删除 SQLite 元数据、Chroma 向量并重建 BM25 索引。

#### `POST /api/v1/documents/{document_id}/reprocess`

重新解析并建立索引，用于 Chunk 配置调整后重建。

### 11.3 问答

#### `POST /api/v1/chat`

请求：

```json
{
  "session_id": "optional-existing-session-id",
  "question": "差旅住宿的报销上限是多少？",
  "stream": false
}
```

响应：

```json
{
  "session_id": "ses_...",
  "run_id": "run_...",
  "answer": "根据员工手册，住宿报销上限为……[1]",
  "route": "knowledge",
  "citations": [
    {
      "index": 1,
      "document_id": "doc_...",
      "chunk_id": "chk_...",
      "filename": "employee-handbook.pdf",
      "heading_path": "费用管理 / 差旅报销",
      "page_number": 12,
      "snippet": "……",
      "rerank_score": 0.93
    }
  ],
  "tool_calls": [],
  "trace_id": "..."
}
```

#### `POST /api/v1/chat/stream`

使用 Server-Sent Events：

```text
event: route
data: {"route": "knowledge"}

event: retrieval
data: {"count": 5}

event: token
data: {"content": "根据"}

event: citation
data: {"index": 1, "filename": "employee-handbook.pdf"}

event: done
data: {"run_id": "run_...", "trace_id": "..."}

event: error
data: {"code": "UPSTREAM_MODEL_ERROR", "message": "..."}
```

SSE 约定：

1. 响应头设置 `X-Accel-Buffering: no`。
2. 输出开始后不能切换为普通 JSON 错误，只能发送 `error` 事件。
3. 前端做 token 展示节流，避免高频 DOM 更新。
4. 客户端断开时取消模型流式请求并记录中断状态。

### 11.4 会话

- `GET /api/v1/sessions`
- `POST /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `GET /api/v1/sessions/{session_id}/messages`
- `DELETE /api/v1/sessions/{session_id}`

首版固定单用户，但所有接口预留 `user_id` 校验位置。

### 11.5 工具

#### `GET /api/v1/tools`

返回普通工具和 MCP 工具：

```json
{
  "tools": [
    {
      "name": "calculate_business_days",
      "source": "mcp",
      "description": "计算工作日",
      "input_schema": {}
    }
  ],
  "trace_id": "..."
}
```

#### `POST /api/v1/tools/{tool_name}/invoke`

只供 Demo 页面调试，使用与 Agent 相同的参数校验、超时和追踪逻辑。

### 11.6 运行诊断

#### `GET /api/v1/runs/{run_id}`

返回：

- 路由结果。
- 每个节点状态和耗时。
- 检索、融合、Rerank 结果。
- 工具调用记录。
- 模型调用耗时和 Token 使用量（供应商返回时）。
- 错误链分类结果。

### 11.7 错误结构

```json
{
  "error": {
    "code": "RAG_NOT_READY",
    "message": "知识库尚未建立索引",
    "request_id": "req_..."
  },
  "trace_id": "..."
}
```

建议错误码：

| HTTP | Code | 场景 |
|---|---|---|
| 400 | `INVALID_REQUEST` | 参数非法 |
| 404 | `DOCUMENT_NOT_FOUND` | 文档不存在 |
| 404 | `SESSION_NOT_FOUND` | 会话不存在 |
| 409 | `DOCUMENT_NOT_READY` | 文档仍在处理 |
| 413 | `FILE_TOO_LARGE` | 文件超限 |
| 422 | `UNSUPPORTED_FILE_TYPE` | 文件格式不支持 |
| 429 | `UPSTREAM_RATE_LIMITED` | 模型供应商限流 |
| 500 | `INTERNAL_ERROR` | 未分类内部错误 |
| 502 | `UPSTREAM_MODEL_ERROR` | 模型接口异常 |
| 503 | `SERVICE_NOT_CONFIGURED` | 必需配置缺失 |
| 503 | `RAG_NOT_READY` | 索引尚未就绪 |

异常分类沿异常链遍历 `__cause__` 和 `__context__`，使用 `visited` 集合防止循环，并映射到稳定错误码。HTTP 状态码由应用错误类型决定，不直接透传供应商状态。

---

## 12. 配置设计

`.env.example` 计划包含：

```dotenv
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000
LOG_LEVEL=INFO
DATA_DIR=./data

AGENT_MODEL=mimo-v2.6-flash
AGENT_TEMPERATURE=0.2
AGENT_MAX_TOKENS=1200
OPENAI_API_KEY=replace_me
OPENAI_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1

SILICONFLOW_API_KEY=replace_me
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=BAAI/bge-m3
RERANK_MODEL=BAAI/bge-reranker-v2-m3

CHUNK_SIZE=800
CHUNK_OVERLAP=120
BM25_CANDIDATE_COUNT=20
VECTOR_CANDIDATE_COUNT=20
RRF_K=60
RERANK_CANDIDATE_COUNT=20
FINAL_CONTEXT_COUNT=5
RERANK_SCORE_THRESHOLD=auto

MODEL_TIMEOUT_SECONDS=60
MODEL_MAX_RETRIES=3
TOOL_TIMEOUT_SECONDS=10
MAX_TOOL_CALLS=5
MAX_UPLOAD_SIZE_MB=10

MCP_ENABLED=true
MCP_SERVER_COMMAND=uv
MCP_SERVER_ARGS=run,mcp_server.py
OTEL_ENABLED=false
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
```

配置在应用启动时校验：

1. URL 必须是合法 HTTPS URL，本地地址除外。
2. 数值范围必须合法。
3. 必需 API Key 缺失时，`/ready` 返回未就绪。
4. 不能在日志中打印完整配置。
5. Rerank 阈值若为 `auto`，由评估样例生成初始值并写入运行配置。

---

## 13. 目录结构

```text
knowledge-search-app/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── documents.py
│   │   ├── chat.py
│   │   ├── sessions.py
│   │   ├── tools.py
│   │   ├── runs.py
│   │   └── health.py
│   ├── agents/
│   │   ├── graph.py
│   │   ├── state.py
│   │   ├── nodes.py
│   │   ├── routing.py
│   │   └── prompts.py
│   ├── rag/
│   │   ├── loaders.py
│   │   ├── splitter.py
│   │   ├── embeddings.py
│   │   ├── vector_store.py
│   │   ├── bm25.py
│   │   ├── fusion.py
│   │   ├── reranker.py
│   │   └── retrieval.py
│   ├── mcp/
│   │   ├── client.py
│   │   └── adapter.py
│   ├── services/
│   │   ├── document_service.py
│   │   ├── chat_service.py
│   │   ├── session_service.py
│   │   └── tool_service.py
│   ├── models/
│   │   ├── api.py
│   │   ├── domain.py
│   │   └── errors.py
│   ├── db/
│   │   ├── database.py
│   │   ├── models.py
│   │   └── migrations/
│   ├── observability/
│   │   ├── logging.py
│   │   └── tracing.py
│   ├── tools/
│   │   ├── calculator.py
│   │   ├── current_time.py
│   │   └── knowledge.py
│   └── config.py
├── mcp_server/
│   ├── server.py
│   └── fixtures/
├── web/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── fixtures/
├── evaluation/
│   ├── cases.jsonl
│   ├── evaluate_retrieval.py
│   └── evaluate_answers.py
├── data/
│   ├── app.db
│   ├── chroma/
│   ├── bm25/
│   └── uploads/
├── docs/
│   ├── DEVELOPMENT.md
│   └── API.md
├── .env.example
├── .gitignore
├── Dockerfile
├── compose.yaml
├── pyproject.toml
├── uv.lock
└── README.md
```

模块依赖方向固定为：

```text
api -> services -> agents/rag/tools -> models/db
```

API 层不直接访问数据库和向量库，RAG 层不依赖 FastAPI。

---

## 14. 可观测性设计

### 14.1 结构化日志

每条日志至少包含：

- `timestamp`
- `level`
- `event`
- `trace_id`
- `run_id`
- `session_id`
- `component`
- `duration_ms`
- `status`
- `error_code`

禁止记录：

- 完整 API Key。
- 完整上传文件内容。
- 未限长的模型 Prompt。
- 未限长的工具输出。
- Authorization Header。

### 14.2 Trace Span

建议 Span 树：

```text
POST /api/v1/chat
├── session.load
├── agent.route
├── query.rewrite
├── rag.retrieve
│   ├── bm25.search
│   └── vector.search
├── rag.rrf
├── rag.rerank
├── tool.execute
│   └── mcp.call
├── model.generate
└── response.finalize
```

每个 Span 记录耗时、状态和非敏感属性，例如候选数量、Chunk ID、工具名和 Token 用量。

### 14.3 指标

首版先记录可导出的基础指标：

- 请求总数和错误数。
- 端到端延迟。
- 检索、Rerank、模型、工具耗时。
- 工具调用成功率。
- 无答案率。
- Token 使用量。
- 文档处理耗时。

### 14.4 Jaeger

提供可选 Compose Profile 启动 Jaeger。应用通过 OTLP 导出 Trace。关闭 `OTEL_ENABLED` 时，系统仍通过结构化日志保留 `trace_id` 和节点执行摘要。

---

## 15. 前端 Demo 页面

页面为单页静态应用，分为三部分：

1. 知识库
   - 选择并上传文档。
   - 显示处理状态、Chunk 数量和错误。
   - 支持删除与重建索引。

2. 对话
   - 新建会话和切换历史会话。
   - 输入问题。
   - 支持普通响应和 SSE 流式响应。
   - 展示回答、引用来源、路由、工具调用和 Trace ID。
   - 点击引用展开命中片段。

3. 诊断
   - 输入 `run_id` 查看执行链。
   - 展示 BM25、向量、融合和 Rerank 排名。
   - 展示工具输入、输出摘要和耗时。

界面不要求复杂视觉设计，但必须满足：

- 无 JavaScript 构建步骤。
- 响应式布局。
- 清晰加载、空、错误状态。
- API Key 不进入浏览器端。
- 文档内容不写入第三方分析服务。

---

## 16. 安全设计

首版至少实现：

1. 文件扩展名、MIME 和大小校验。
2. 文件名安全化，禁止路径穿越。
3. 上传文件存储在独立 `data/uploads`。
4. Prompt 与文档内容分隔，明确文档是数据而不是指令。
5. 工具参数 Schema 校验。
6. 工具输出限长和 HTML 转义。
7. API Key 脱敏。
8. 上游异常不透传完整响应。
9. CORS 默认仅允许本地 Demo 来源。
10. `.env`、`data/` 和运行日志加入 `.gitignore`。
11. DELETE 操作只允许操作明确 ID。
12. 文档删除同时清理向量和元数据。

首版无鉴权，因此 README 必须明确“只能用于本地演示，不应直接暴露公网”。

---

## 17. 测试计划

### 17.1 单元测试

- 文本规范化。
- Markdown/PDF/TXT 解析。
- Chunk 边界和标题路径。
- BM25 中文分词。
- RRF 融合排序。
- Rerank 阈值和空结果。
- 路由结构化解析。
- 引用编号校验。
- 计算器安全解析。
- 异常链错误分类。
- 配置校验。

### 17.2 集成测试

使用 Fake Chat Model、Fake Embedder、Fake Reranker，避免测试消耗真实 API：

- 文档上传到可问答状态。
- 多轮上下文查询重写。
- Knowledge 路由生成引用。
- Tool 路由执行普通工具。
- Hybrid 路由合并证据。
- MCP Tool 参数和超时处理。
- 会话历史读取和删除。
- 索引删除重建。
- 上游失败返回稳定错误码。

### 17.3 API 测试

- 正常请求状态码和响应 Schema。
- 文件格式、大小和空文件错误。
- 不存在的文档、会话和运行。
- SSE 正常结束与错误事件。
- `trace_id` 在响应和日志中一致。

### 17.4 MCP 契约测试

- Tool 列表发现。
- 输入 Schema。
- 正常调用。
- 参数非法。
- 超时。
- Server 启动失败。
- 输出限长。

### 17.5 真实模型 Smoke Test

默认不进入单元测试，只在显式提供密钥时运行：

1. 调用聊天模型生成一句话。
2. 调用 `BAAI/bge-m3` 生成向量并检查维度一致。
3. 调用 `BAAI/bge-reranker-v2-m3` 检查排序结果。
4. MCP Server 启动并列出工具。

Smoke Test 不能打印真实 API Key。

### 17.6 评估用例

准备至少 20 条问题，覆盖：

- 单文档事实问题。
- 跨文档问题。
- 表格或数值问题。
- 多轮指代问题。
- 需要普通工具的问题。
- 需要 MCP 工具的问题。
- 混合问题。
- 知识库无答案问题。
- 容易产生幻觉的问题。

检索指标：

- Recall@K。
- MRR。
- Rerank 前后排名变化。
- 无答案拒绝准确率。

答案质量首版采用规则检查加人工抽样：

- 引用存在率。
- 引用编号有效率。
- 拒答正确率。
- 答案与来源可核对性。
- 工具结果使用正确率。

---

## 18. 开发里程碑

### 阶段 0：工程初始化

- 创建 `uv` Python 3.11 项目。
- 配置依赖、格式化、测试和 `.gitignore`。
- 创建配置系统和 `.env.example`。
- 初始化 FastAPI、SQLite 和结构化日志。
- 完成 `/health`、`/ready`。

验收：服务可以启动，测试可以运行，配置缺失会给出明确错误。

### 阶段 1：文档与 RAG 基础

- 文档上传、解析、切分和元数据保存。
- BGE-M3 Embedding 适配器。
- Chroma 向量存储。
- BM25 索引。
- RRF 融合。
- BGE Reranker 适配器。
- 基础检索服务。

验收：上传样例文档后，能够返回混合检索和 Rerank 结果。

### 阶段 2：Agent、工具与 MCP

- LangGraph StateGraph。
- 结构化意图路由。
- 多轮查询重写。
- 普通工具实现。
- MCP Server/Client。
- 工具超时、限制和追踪。
- 回答生成与引用校验。

验收：知识、工具、混合、澄清和无答案五类问题均能走正确路径。

### 阶段 3：FastAPI 与 Web Demo

- 完整文档、聊天、会话、工具和诊断接口。
- 普通 JSON 问答与 SSE。
- 静态 Web 页面。
- 统一错误处理。
- 会话状态保存。

验收：只通过浏览器即可完成上传、提问、查看引用、工具调用和追踪。

### 阶段 4：测试、评估与可观测性

- 单元、集成、API、MCP 契约测试。
- 真实模型 Smoke Test。
- 检索和答案评估脚本。
- OpenTelemetry Span。
- 可选 Jaeger。
- 性能和超时配置。

验收：离线测试稳定通过，真实模型测试可以独立执行，Trace 可以还原请求过程。

### 阶段 5：交付整理

- README 和 API 文档。
- 示例文档和示例问题。
- Dockerfile/Compose 可选运行方式。
- 启动脚本和常见问题。
- 已知限制与后续路线。

验收：新环境按照 README 可以复现完整 Demo。

---

## 19. 完成定义

项目只有同时满足以下条件才算 Demo 完成：

1. `uv run` 可以安装并启动服务。
2. 可以上传至少 TXT、Markdown、PDF 三种文档。
3. 文档能够完成切分、Embedding、索引和状态管理。
4. 检索结果同时体现 BM25、向量、RRF 和 Rerank。
5. LangGraph 能够展示条件路由和多轮状态。
6. 至少一个普通工具和两个 MCP 工具可以被调用。
7. 回答包含可展开的有效引用。
8. 无答案问题能够正确拒答。
9. FastAPI 提供完整 JSON API 和 SSE。
10. Web 页面可完成端到端演示。
11. 每个请求具有可查询的 `trace_id` 和运行记录。
12. API Key 不进入代码、文档、日志和 Git。
13. 单元、集成、API 和 MCP 测试通过。
14. 真实模型 Smoke Test 通过。
15. README 能指导第三方完成配置、启动、导入知识和演示。

---

## 20. 当前还需要补充或确认的信息

### 20.1 必须补充

1. **样例知识文档**
   - 最好提供 10～20 份 Markdown/TXT 和 2～3 份 PDF。
   - 如果暂时没有，将创建一套虚构的“员工制度、产品说明、项目管理规范”测试数据。

2. **验收问题集**
   - 至少 20 个问题和期望答案。
   - 如果暂时没有，将由 Demo 自动生成并人工确认。

3. **密钥安全确认**
   - 当前提供的 Key 不应继续粘贴到聊天、代码或 Git。
   - 如果这些 Key 有较高配额或用于其他项目，建议在配置完成后确认是否需要单独轮换。

### 20.2 建议确认但不阻塞

1. Web 页面是否需要更丰富的交互。
2. 是否要求 SSE 流式输出，当前默认“需要”。
3. 是否需要 Docker 运行，当前默认“提供可选 Dockerfile/Compose”。
4. 是否需要 OpenTelemetry/Jaeger，当前默认“日志必做、OTel 可选”。
5. 是否需要真实企业权限，当前默认“不做，仅预留接口”。
6. 是否希望复用历史 `46_enterprise_agent` 的代码。
   - 当前建议：复用设计经验和测试思路，不直接复制旧代码，以保持本项目结构清晰。

### 20.3 已知技术风险

| 风险 | 等级 | 处理方式 |
|---|---|---|
| 两家供应商网络或服务不稳定 | 中 | 重试、超时、稳定错误码、离线 Fake 测试 |
| 模型不严格遵守引用格式 | 中 | Prompt 约束、引用编号后校验、必要时修复 |
| 中文 BM25 分词效果不足 | 中 | jieba、标题关键词加权、评估后调整 |
| Rerank 分数阈值难统一 | 中 | 样例集校准并配置化 |
| 多轮查询重写引入错误 | 中 | 仅在需要时改写，保留原查询用于日志 |
| MCP 进程异常或阻塞 | 中 | 启动检测、超时、健康状态、错误隔离 |
| PDF 文本层质量差 | 中 | 首版明确不支持 OCR，记录解析质量 |
| 长文档上下文超预算 | 中 | Rerank 后限长、保留标题和来源 |
| LangChain/LangGraph API 演进 | 中 | 锁定依赖版本并保留兼容测试 |
| Demo 暴露公网造成数据泄露 | 高 | 默认只监听 `127.0.0.1`，文档明确风险 |

---

## 21. 建议实施顺序

下一步不应先写 Agent，而应按依赖顺序推进：

1. 确认本开发文档范围。
2. 初始化 Python 3.11、依赖、配置、日志和 FastAPI。
3. 完成真实模型连接 Smoke Test。
4. 完成文档入库和单路检索。
5. 完成混合检索和 Rerank。
6. 完成 LangGraph 路由与回答生成。
7. 完成普通工具和 MCP。
8. 完成 API、SSE 和 Web 页面。
9. 完成测试、评估、追踪和交付文档。

这样可以尽早验证最不确定的模型接口，再逐步叠加 Agent 和产品能力。
