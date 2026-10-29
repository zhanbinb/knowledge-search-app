from __future__ import annotations

from dataclasses import dataclass

from app.agents.graph import KnowledgeAgentGraph
from app.config import Settings
from app.db.database import Database
from app.mcp_client import MCPToolClient
from app.rag.bm25 import BM25Index
from app.rag.embeddings import EmbeddingClient, RerankClient
from app.rag.retrieval import HybridRetriever
from app.rag.vector_store import VectorStore
from app.services.chat_service import ChatService
from app.services.document_service import DocumentService
from app.tools.registry import ToolRegistry


@dataclass
class ApplicationContainer:
    settings: Settings
    database: Database
    embedding_client: EmbeddingClient
    rerank_client: RerankClient
    vector_store: VectorStore
    bm25_index: BM25Index
    retriever: HybridRetriever
    mcp_client: MCPToolClient
    tool_registry: ToolRegistry
    agent: KnowledgeAgentGraph
    document_service: DocumentService
    chat_service: ChatService

    @classmethod
    def create(cls, settings: Settings) -> "ApplicationContainer":
        settings.ensure_directories()
        database = Database(settings.database_path)
        embedding_client = EmbeddingClient(settings)
        rerank_client = RerankClient(settings)
        vector_store = VectorStore(settings, embedding_client)
        bm25_index = BM25Index()
        retriever = HybridRetriever(
            settings, embedding_client, rerank_client, vector_store, bm25_index
        )
        retriever.rebuild_index(database.all_chunks())
        mcp_client = MCPToolClient(settings)
        tool_registry = ToolRegistry(settings, mcp_client)
        agent = KnowledgeAgentGraph(settings, retriever, tool_registry)
        document_service = DocumentService(
            settings, database, vector_store, retriever
        )
        chat_service = ChatService(settings, database, agent)
        return cls(
            settings=settings,
            database=database,
            embedding_client=embedding_client,
            rerank_client=rerank_client,
            vector_store=vector_store,
            bm25_index=bm25_index,
            retriever=retriever,
            mcp_client=mcp_client,
            tool_registry=tool_registry,
            agent=agent,
            document_service=document_service,
            chat_service=chat_service,
        )

    def close(self) -> None:
        self.database.close()
