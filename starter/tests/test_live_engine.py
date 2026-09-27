from __future__ import annotations

import json

from kbqa.llm import LLMReply
from kbqa.service import Service
from kbqa.trace import Trace


class FakeLiveClient:
    def __init__(self):
        self.calls: list[list[dict]] = []
        self.round = 0

    def chat_with_retry(self, messages, tools, budget=None, on_call=None):
        self.calls.append(json.loads(json.dumps(messages, ensure_ascii=False)))
        if self.round == 0:
            self.round += 1
            message = {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "need data and target",
                    "tool_calls": [
                        {
                            "id": "call-metrics",
                            "type": "function",
                            "function": {
                                "name": "query_metrics",
                                "arguments": json.dumps(
                                    {
                                        "start": "2026-06-18",
                                        "end": "2026-06-18",
                                        "store_id": "S02",
                                        "product_id": "P06",
                                    }
                                ),
                            },
                        },
                        {
                            "id": "call-kb",
                            "type": "function",
                            "function": {
                                "name": "search_kb",
                                "arguments": json.dumps({"query": "618 牛肉poke 目标销量"}),
                            },
                        },
                    ],
                }
            reply = LLMReply(
                message=message,
                finish_reason="tool_calls",
                content="",
                tool_calls=message["tool_calls"],
                elapsed=0.01,
            )
        else:
            reply = LLMReply(
                message={"role": "assistant", "content": "实际售出 125 份，目标 120 份，已达标。[KB-023]"},
                finish_reason="stop",
                content="实际售出 125 份，目标 120 份，已达标。[KB-023]",
                tool_calls=[],
                elapsed=0.01,
            )
        if on_call:
            on_call({"request": {"messages": messages}, "round": self.round})
        return reply


def test_live_engine_replays_reasoning_and_supports_multiple_tools():
    from kbqa.live import LiveEngine

    service = Service()
    plan = service.planner.plan("618 当天 S02 的牛肉poke 卖了多少份？达到目标了吗？", [])
    fake = FakeLiveClient()
    trace = Trace("live-test", plan.question, "live-session")
    engine = LiveEngine(
        fake,
        service.answerer,
        service.run_tool,
        service.settings.today.isoformat(),
        service.data_period,
        budget=30,
    )
    answer = engine.answer(plan, trace, [])
    assert answer.answer_type == "hybrid"
    assert answer.data_evidence
    assert answer.citations and answer.citations[0]["doc_id"] == "KB-023"
    assert len(fake.calls) == 2
    assert any("initial_retrieval" in message.get("content", "") for message in fake.calls[0] if message.get("role") == "system")
    second = fake.calls[1]
    assistant = next(message for message in second if message.get("role") == "assistant")
    assert assistant["reasoning_content"] == "need data and target"
    assert len([message for message in second if message.get("role") == "tool"]) == 2
    assert any(step["step"] == "final_validation" for step in trace.steps)
