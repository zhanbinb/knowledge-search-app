from app.rag.documents import ParsedDocument
from app.rag.splitter import split_document


def test_splitter_preserves_metadata_and_overlap():
    text = "# 制度\n" + ("这是一段用于测试切分的企业知识内容。" * 80)
    parsed = ParsedDocument(text=text, page_count=1, page_offsets=[(0, len(text), 1)], file_type="md")

    chunks = split_document(parsed, chunk_size=240, chunk_overlap=40)

    assert chunks
    assert chunks[0]["heading_path"] == "制度"
    assert all(chunk["page_number"] == 1 for chunk in chunks)
    assert chunks[0]["content"]
