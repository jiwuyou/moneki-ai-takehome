"""Two-stage retrieval for live conversations.

The code performs a cheap initial retrieval first.  The model may then issue
one refined ``search_kb`` query after seeing the preliminary snippets.  Both
results use the same Retriever implementation and are retained in trace.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class InitialRetrieval:
    query: str
    results: list[dict]


def initial_retrieval(answerer, plan, trace, limit: int = 5) -> InitialRetrieval:
    query = plan.search_query or plan.standalone or plan.question
    if not plan.needs_docs or not query:
        return InitialRetrieval(query, [])
    started = time.perf_counter()
    result = answerer.retriever.search(
        query,
        top_k=limit,
        as_of=plan.as_of,
        store_id=plan.store_id,
        year=plan.year,
        window=plan.window,
        numeric=bool(plan.slots.get("metric_explicit")) and plan.needs_data,
        historical=bool(plan.slots.get("historical")),
    )
    payload = result.as_trace()
    payload["stage"] = "initial_code_retrieval"
    trace.step("rag_initial", payload, started=started)
    return InitialRetrieval(query, [hit.as_result() for hit in result.ranked[:limit]])


def format_initial_context(initial: InitialRetrieval, max_chars: int = 5000) -> str:
    if not initial.results:
        return ""
    blocks = []
    for item in initial.results:
        blocks.append(
            "doc_id=%s chunk_id=%s score=%s\n%s"
            % (item.get("doc_id"), item.get("chunk_id"), item.get("score"), item.get("text", ""))
        )
    text = "\n\n".join(blocks)
    return text[:max_chars]

