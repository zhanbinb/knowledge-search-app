from __future__ import annotations

from collections import defaultdict
from typing import Any


def reciprocal_rank_fusion(
    result_lists: list[list[dict[str, Any]]],
    *,
    k: int = 60,
) -> list[dict[str, Any]]:
    scores: dict[str, float] = defaultdict(float)
    payloads: dict[str, dict[str, Any]] = {}

    for results in result_lists:
        for rank, item in enumerate(results, start=1):
            chunk_id = item["chunk_id"]
            scores[chunk_id] += 1.0 / (k + rank)
            if chunk_id not in payloads:
                payloads[chunk_id] = dict(item)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    output: list[dict[str, Any]] = []
    for chunk_id, score in ranked:
        item = dict(payloads[chunk_id])
        item["score"] = float(score)
        output.append(item)
    return output
