from __future__ import annotations

import asyncio
import json

from langchain_core.messages import HumanMessage

from app.agents.graph import KnowledgeAgentGraph
from app.config import get_settings
from app.container import ApplicationContainer


async def main() -> None:
    settings = get_settings()
    errors = settings.validate_model_configuration()
    if errors:
        raise SystemExit("; ".join(errors))

    container = ApplicationContainer.create(settings)
    try:
        embeddings = container.embedding_client.embed_documents(["企业知识库测试文本"])
        print(json.dumps({"embedding_dimensions": len(embeddings[0])}, ensure_ascii=False))

        reranked = container.rerank_client.rerank(
            "住宿报销标准",
            ["深圳住宿标准为500元", "信息安全制度要求保护密钥"],
            2,
        )
        print(json.dumps({"rerank_results": reranked}, ensure_ascii=False))

        response = await container.agent.model.ainvoke(
            [HumanMessage(content="只回答：连接成功")]
        )
        print(json.dumps({"chat_response": response.content}, ensure_ascii=False))

        tools = await container.mcp_client.list_tools()
        print(json.dumps({"mcp_tools": tools}, ensure_ascii=False))
    finally:
        container.close()


if __name__ == "__main__":
    asyncio.run(main())
