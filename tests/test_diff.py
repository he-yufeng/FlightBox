"""Tests for the diff module."""


import pytest

from flightbox.diff import diff_runs
from flightbox.store import RecordStore


@pytest.fixture
def store(tmp_path):
    return RecordStore(tmp_path / "test.db")


def test_identical_runs(store):
    a = store.create_run(name="a")
    b = store.create_run(name="b")
    for rid in (a, b):
        store.add_event(rid, 1, "llm_call", provider="openai", model="gpt-4o",
                        request={"messages": [{"role": "user", "content": "hi"}]},
                        response={"choices": [{"message": {"content": "hello"}}]})
    assert diff_runs(a, b, store) == []


def test_response_diff(store):
    a = store.create_run(name="a")
    b = store.create_run(name="b")
    store.add_event(a, 1, "llm_call", response={"text": "answer A"})
    store.add_event(b, 1, "llm_call", response={"text": "answer B"})
    diffs = diff_runs(a, b, store)
    assert len(diffs) == 1
    assert diffs[0].field == "response"


def test_ignored_fields_hide_expected_noise(store):
    a = store.create_run(name="a")
    b = store.create_run(name="b")
    store.add_event(a, 1, "llm_call", request={"metadata": {"trace": "a"}}, response={"text": "same"})
    store.add_event(b, 1, "llm_call", request={"metadata": {"trace": "b"}}, response={"text": "same"})

    assert diff_runs(a, b, store, ignored_fields={"request"}) == []


def test_length_diff(store):
    a = store.create_run(name="a")
    b = store.create_run(name="b")
    store.add_event(a, 1, "llm_call")
    store.add_event(a, 2, "llm_call")
    store.add_event(b, 1, "llm_call")
    diffs = diff_runs(a, b, store)
    assert any(d.field == "event" and d.run_b_value is None for d in diffs)
