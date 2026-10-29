from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

from app.config import Settings
from app.db.database import Database
from app.errors import DocumentNotFoundError, FileTooLargeError
from app.rag.documents import calculate_checksum, parse_document
from app.rag.retrieval import HybridRetriever
from app.rag.splitter import split_document
from app.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        vector_store: VectorStore,
        retriever: HybridRetriever,
    ) -> None:
        self.settings = settings
        self.database = database
        self.vector_store = vector_store
        self.retriever = retriever

    def ingest(self, content: bytes, filename: str) -> dict[str, Any]:
        if len(content) > self.settings.max_upload_bytes:
            raise FileTooLargeError(
                f"文件超过 {self.settings.max_upload_size_mb} MB 限制"
            )
        if not content:
            raise FileTooLargeError("文件内容为空")

        checksum = calculate_checksum(content)
        existing = self.database.get_document_by_checksum(checksum)
        if existing:
            return existing

        parsed = parse_document(content, filename)
        document_id = f"doc_{uuid.uuid4().hex}"
        safe_name = self._safe_filename(filename)
        storage_path = self.settings.upload_path / f"{document_id}{Path(safe_name).suffix}"
        storage_path.write_bytes(content)

        document = self.database.create_document(
            document_id=document_id,
            filename=safe_name,
            file_type=parsed.file_type,
            checksum=checksum,
            char_count=len(parsed.text),
            page_count=parsed.page_count,
        )

        try:
            chunks = split_document(
                parsed,
                chunk_size=self.settings.chunk_size,
                chunk_overlap=self.settings.chunk_overlap,
            )
            for chunk in chunks:
                chunk["filename"] = safe_name
            self.database.save_chunks(document_id, chunks)
            self.vector_store.upsert_document(document_id, chunks)
            self.retriever.rebuild_index(self.database.all_chunks())
            document = self.database.update_document(
                document_id, status="READY", chunk_count=len(chunks)
            )
            logger.info(
                "document ingested",
                extra={"component": "document", "status": "READY"},
            )
            return document
        except Exception as exc:
            self.database.update_document(
                document_id, status="FAILED", error_message=str(exc)[:500]
            )
            self.vector_store.delete_document(document_id)
            raise

    def reprocess(self, document_id: str) -> dict[str, Any]:
        document = self.database.get_document(document_id)
        if not document:
            raise DocumentNotFoundError("文档不存在")

        storage_path = self.settings.upload_path / (
            f"{document_id}{Path(document['filename']).suffix}"
        )
        if not storage_path.exists():
            raise DocumentNotFoundError("原始文件已不存在，无法重新处理")

        content = storage_path.read_bytes()
        self.database.delete_document(document_id)
        self.vector_store.delete_document(document_id)
        parsed = parse_document(content, document["filename"])

        self.database.create_document(
            document_id=document_id,
            filename=document["filename"],
            file_type=document["file_type"],
            checksum=document["checksum"],
            char_count=len(parsed.text),
            page_count=parsed.page_count,
        )
        chunks = split_document(
            parsed,
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
        )
        for chunk in chunks:
            chunk["filename"] = document["filename"]
        self.database.save_chunks(document_id, chunks)
        self.vector_store.upsert_document(document_id, chunks)
        self.retriever.rebuild_index(self.database.all_chunks())
        return self.database.update_document(
            document_id, status="READY", chunk_count=len(chunks)
        )

    def delete(self, document_id: str) -> None:
        document = self.database.get_document(document_id)
        if not document:
            raise DocumentNotFoundError("文档不存在")
        self.database.delete_document(document_id)
        self.vector_store.delete_document(document_id)
        self.retriever.rebuild_index(self.database.all_chunks())

    def rebuild_indexes(self) -> dict[str, int]:
        chunks = self.database.all_chunks()
        self.retriever.rebuild_index(chunks)
        return {"chunks": len(chunks), "vectors": self.vector_store.count}

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = Path(filename).name
        name = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]", "_", name)
        return name[:120] or "document"
