from __future__ import annotations

import httpx
import pytest

from kbqa.llm import LLMClient, LLMError


def test_endpoint_preserves_base_path_and_model(monkeypatch):
    seen = {}

    def fake_post(url, *, json, headers, timeout):
        seen.update(url=url, body=json, headers=headers)
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = LLMClient("http://127.0.0.1:1234/ds-gw", "test-key", "test-model")
    trace = []
    reply = client.chat([{"role": "user", "content": "hello"}], on_call=trace.append)
    assert reply.content == "ok"
    assert seen["url"] == "http://127.0.0.1:1234/ds-gw/chat/completions"
    assert seen["body"]["model"] == "test-model"
    assert seen["headers"]["Authorization"] == "Bearer test-key"
    assert "test-key" not in str(trace)
    assert trace[0]["request"]["messages"][0]["content"] == "hello"


@pytest.mark.parametrize("finish", ["length", "content_filter", "insufficient_system_resource", "aborted"])
def test_abnormal_finish_is_error(monkeypatch, finish):
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={"choices": [{"finish_reason": finish, "message": {"content": "partial"}}]},
        ),
    )
    with pytest.raises(LLMError):
        LLMClient("http://x", "test", "m").chat([{"role": "user", "content": "x"}])
