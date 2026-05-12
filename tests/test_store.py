"""Tests for the RecordStore."""

import json

import pytest

from flightbox.store import RecordStore


@pytest.fixture
def store(tmp_path):
    return RecordStore(tmp_path / "test.db")


def test_create_and_list_runs(store):
    r1 = store.create_run(name="first")
    r2 = store.create_run(name="second")
    runs = store.list_runs()
    assert len(runs) == 2
    ids = {r["run_id"] for r in runs}
    assert r1 in ids and r2 in ids


def test_finish_run(store):
    rid = store.create_run(name="test")
    run = store.get_run(rid)
    assert run["finished_at"] is None
    store.finish_run(rid)
    run = store.get_run(rid)
    assert run["finished_at"] is not None


def test_add_and_get_events(store):
    rid = store.create_run()
    store.add_event(rid, 1, "llm_call", provider="openai", model="gpt-4o",
                    request={"messages": [{"role": "user", "content": "hi"}]},
                    response={"choices": [{"message": {"content": "hello"}}]},
                    latency_ms=150.5,
                    token_usage={"prompt_tokens": 10, "completion_tokens": 5})
    store.add_event(rid, 2, "llm_call", provider="openai", model="gpt-4o",
                    request={"messages": []}, error="Timeout")

    events = store.get_events(rid)
    assert len(events) == 2
    assert events[0]["seq"] == 1
    assert events[0]["latency_ms"] == pytest.approx(150.5)
    assert json.loads(events[0]["token_usage"])["prompt_tokens"] == 10
    assert events[1]["error"] == "Timeout"


def test_delete_run(store):
    rid = store.create_run(name="deleteme")
    store.add_event(rid, 1, "llm_call")
    store.delete_run(rid)
    assert store.get_run(rid) is None
    assert store.get_events(rid) == []


def test_event_count(store):
    rid = store.create_run()
    assert store.get_event_count(rid) == 0
    for i in range(5):
        store.add_event(rid, i + 1, "llm_call")
    assert store.get_event_count(rid) == 5


def test_run_metadata(store):
    rid = store.create_run(name="meta", metadata={"env": "prod", "version": 2})
    run = store.get_run(rid)
    meta = json.loads(run["metadata"])
    assert meta["env"] == "prod"
    assert meta["version"] == 2


def test_run_stats(store):
    rid = store.create_run(name="stats")
    store.add_event(
        rid,
        1,
        "llm_call",
        latency_ms=100,
        token_usage={"prompt_tokens": 10, "completion_tokens": 5},
    )
    store.add_event(
        rid,
        2,
        "llm_call",
        latency_ms=300,
        token_usage={"input_tokens": 2, "output_tokens": 3},
        error="timeout",
    )

    stats = store.get_run_stats(rid)

    assert stats["events"] == 2
    assert stats["llm_calls"] == 2
    assert stats["errors"] == 1
    assert stats["prompt_tokens"] == 12
    assert stats["completion_tokens"] == 8
    assert stats["total_tokens"] == 20
    assert stats["latency_ms_avg"] == pytest.approx(200)
