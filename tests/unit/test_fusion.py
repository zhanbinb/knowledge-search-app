from app.rag.fusion import reciprocal_rank_fusion


def test_rrf_fuses_and_orders_results():
    left = [
        {"chunk_id": "a", "content": "A"},
        {"chunk_id": "b", "content": "B"},
    ]
    right = [
        {"chunk_id": "b", "content": "B"},
        {"chunk_id": "c", "content": "C"},
    ]

    result = reciprocal_rank_fusion([left, right], k=60)

    assert result[0]["chunk_id"] == "b"
    assert {item["chunk_id"] for item in result} == {"a", "b", "c"}
    assert result[0]["score"] > result[1]["score"]
