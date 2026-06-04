from flightbox.store import RecordStore
from flightbox.timeline import build_timeline, render_timeline_markdown


def test_timeline_redacts_and_summarizes_events(tmp_path):
    store = RecordStore(tmp_path / "recordings.db")
    run_id = store.create_run(name="timeline")
    store.add_event(
        run_id,
        1,
        "llm_call",
        provider="openai",
        model="gpt-4o",
        request={"headers": {"Authorization": "Bearer secret-token-value"}},
        response={"content": "ok"},
        latency_ms=125,
        token_usage={"prompt_tokens": 3, "completion_tokens": 4},
    )

    rows = build_timeline(run_id, store)
    text = render_timeline_markdown(run_id, rows)

    assert rows[0]["tokens"] == 7
    assert "125ms" in text
    assert "<REDACTED>" in text
    assert "secret-token-value" not in text
