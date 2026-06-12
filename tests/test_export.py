"""Tests for the export module."""

import json

import pytest

from flightbox.export import export_jsonl, export_pytest
from flightbox.store import RecordStore


@pytest.fixture
def store(tmp_path):
    return RecordStore(tmp_path / "test.db")


@pytest.fixture
def sample_run(store):
    rid = store.create_run(name="export-test")
    store.add_event(
        rid, 1, "llm_call", provider="openai", model="gpt-4o",
        request={"messages": [{"role": "user", "content": "What is 2+2?"}], "tools": [{"type": "function"}]},
        response={"choices": [{"message": {"content": "4"}}]},
    )
    store.add_event(
        rid, 2, "llm_call", provider="openai", model="gpt-4o",
        request={"messages": [{"role": "user", "content": "Thanks"}]},
        response={"choices": [{"message": {"content": "You're welcome"}}]},
    )
    return rid


def test_export_jsonl(store, sample_run, tmp_path):
    out = tmp_path / "export.jsonl"
    count = export_jsonl(sample_run, out, store)
    assert count == 2
    lines = out.read_text().strip().split("\n")
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["messages"][0]["content"] == "What is 2+2?"
    assert "tools" in first
    assert "expected_response" in first


def test_export_jsonl_redacts_secrets_by_default(store, tmp_path):
    run_id = store.create_run(name="secret-export")
    store.add_event(
        run_id,
        1,
        "llm_call",
        provider="openai",
        model="gpt-4o",
        request={
            "api_key": "sk-" + ("a" * 24),
            "messages": [{"role": "user", "content": "token test"}],
        },
        response={"Authorization": "Bearer tokenvalue123456789"},
    )

    out = tmp_path / "export.jsonl"
    export_jsonl(run_id, out, store)

    text = out.read_text(encoding="utf-8")
    assert "sk-" not in text
    assert "tokenvalue123456789" not in text
    assert "<REDACTED>" in text


def test_export_jsonl_raw_keeps_payloads_when_requested(store, tmp_path):
    run_id = store.create_run(name="raw-export")
    key = "sk-" + ("b" * 24)
    store.add_event(
        run_id,
        1,
        "llm_call",
        provider="openai",
        model="gpt-4o",
        request={"messages": [{"role": "user", "content": key}]},
        response={"choices": [{"message": {"content": "ok"}}]},
    )

    out = tmp_path / "export.jsonl"
    export_jsonl(run_id, out, store, redact_secrets=False)

    assert key in out.read_text(encoding="utf-8")


def test_export_pytest(store, sample_run, tmp_path):
    out = tmp_path / "test_replay.py"
    count = export_pytest(sample_run, out, store)
    assert count == 2
    code = out.read_text(encoding="utf-8")
    assert "flightbox.replay" in code
    assert sample_run in code
    assert "def test_replay_" in code
