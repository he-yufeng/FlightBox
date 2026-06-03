from flightbox.report import build_report, render_markdown, write_report
from flightbox.store import RecordStore


def test_report_redacts_secrets(tmp_path):
    store = RecordStore(tmp_path / "recordings.db")
    run_id = store.create_run(name="secret-run")
    store.add_event(
        run_id,
        1,
        "llm_call",
        provider="openai",
        model="gpt-4o",
        request={"headers": {"Authorization": "Bearer tokenvalue123456789"}},
        response={"content": "ok", "api_key": "plainsecret123456789"},
        token_usage={"prompt_tokens": 1, "completion_tokens": 1},
    )

    report = build_report(run_id, store)
    text = render_markdown(report)

    assert "tokenvalue" not in text
    assert "plainsecret" not in text
    assert "<REDACTED>" in text


def test_write_report_html(tmp_path):
    store = RecordStore(tmp_path / "recordings.db")
    run_id = store.create_run(name="html-run")
    store.add_event(run_id, 1, "llm_call", request={"messages": []}, response={"ok": True})

    out = tmp_path / "report.html"
    write_report(run_id, out, fmt="html", store=store)

    assert out.exists()
    assert "<!doctype html>" in out.read_text(encoding="utf-8")
