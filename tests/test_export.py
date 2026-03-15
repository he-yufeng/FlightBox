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


def test_export_pytest(store, sample_run, tmp_path):
    out = tmp_path / "test_replay.py"
    count = export_pytest(sample_run, out, store)
    assert count == 2
    code = out.read_text()
    assert "flightbox.replay" in code
    assert sample_run in code
    assert "def test_replay_" in code
