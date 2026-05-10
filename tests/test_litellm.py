import asyncio
import json
import sys
import types

import pytest

from flightbox import record, replay
from flightbox.store import RecordStore


@pytest.fixture
def fake_litellm(monkeypatch):
    module = types.SimpleNamespace()

    def completion(**kwargs):
        return {
            "id": "chatcmpl-test",
            "model": kwargs["model"],
            "choices": [{"message": {"role": "assistant", "content": "hello"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        }

    async def acompletion(**kwargs):
        return {
            "id": "chatcmpl-async-test",
            "model": kwargs["model"],
            "choices": [{"message": {"role": "assistant", "content": "async hello"}}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2},
        }

    module.completion = completion
    module.acompletion = acompletion
    monkeypatch.setitem(sys.modules, "litellm", module)
    return module


def test_records_litellm_completion(fake_litellm, tmp_path):
    store = RecordStore(tmp_path / "recordings.db")
    with record("litellm-sync", store=store) as rec:
        response = fake_litellm.completion(
            model="openrouter/test-model",
            messages=[{"role": "user", "content": "hi"}],
        )

    events = store.get_events(rec.run_id)
    assert response["choices"][0]["message"]["content"] == "hello"
    assert len(events) == 1
    assert events[0]["provider"] == "litellm"
    assert events[0]["model"] == "openrouter/test-model"
    assert json.loads(events[0]["request"])["messages"][0]["content"] == "hi"


def test_replays_litellm_completion(fake_litellm, tmp_path):
    store = RecordStore(tmp_path / "recordings.db")
    run_id = store.create_run("replay")
    store.add_event(
        run_id,
        1,
        "llm_call",
        provider="litellm",
        model="openrouter/test-model",
        response={
            "choices": [{"message": {"role": "assistant", "content": "from tape"}}],
        },
    )

    with replay(run_id, store=store):
        response = fake_litellm.completion(
            model="openrouter/test-model",
            messages=[{"role": "user", "content": "hi"}],
        )

    assert response["choices"][0]["message"]["content"] == "from tape"


def test_records_and_replays_litellm_acompletion(fake_litellm, tmp_path):
    async def run():
        store = RecordStore(tmp_path / "recordings.db")
        with record("litellm-async", store=store) as rec:
            response = await fake_litellm.acompletion(
                model="openrouter/test-model",
                messages=[{"role": "user", "content": "hi"}],
            )
        assert response["choices"][0]["message"]["content"] == "async hello"

        with replay(rec.run_id, store=store):
            replayed = await fake_litellm.acompletion(
                model="openrouter/test-model",
                messages=[{"role": "user", "content": "hi"}],
            )
        assert replayed["choices"][0]["message"]["content"] == "async hello"

    asyncio.run(run())
