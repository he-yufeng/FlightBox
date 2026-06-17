import json

from flightbox.audit import audit_run, render_audit_markdown, write_audit
from flightbox.report import (
    build_report,
    parse_environment_items,
    redact,
    render_markdown,
    write_report,
)
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


def test_redact_masks_cloud_provider_key_values():
    # assemble the secret-shaped values at runtime so the literals never sit in
    # the source verbatim — committing them as-is would trip secret scanners.
    aws = "AKIA" + "1234567890ABCDEF"
    google = "AIza" + "B" * 35
    slack = "xoxb-" + "1234567890" + "-abcdefghijklmnop"
    out = redact(
        {
            "aws": f"creds {aws} here",
            "google": google,
            "slack": slack,
        }
    )
    blob = json.dumps(out)
    assert "1234567890ABCDEF" not in blob
    assert "B" * 35 not in blob
    assert "abcdefghijklmnop" not in blob
    assert "<REDACTED>" in blob


def test_redact_masks_pem_private_key_block():
    # split the PEM markers so the verbatim header/footer aren't committed.
    begin = "-----BEGIN RSA " + "PRIVATE KEY-----"
    end = "-----END RSA " + "PRIVATE KEY-----"
    pem = f"{begin}\nFAKEKEYMATERIALfakekeymaterial1234567890abcdef\n{end}"
    out = redact({"note": f"leaked:\n{pem}"})
    assert "fakekeymaterial" not in out["note"]
    assert "<REDACTED>" in out["note"]


def test_redact_keeps_token_counts():
    # token *counts* are evidence, not secrets — they must survive redaction
    out = redact({"usage": {"prompt_tokens": 123, "total_tokens": 456}})
    assert out["usage"]["prompt_tokens"] == 123
    assert out["usage"]["total_tokens"] == 456


def test_write_report_html(tmp_path):
    store = RecordStore(tmp_path / "recordings.db")
    run_id = store.create_run(name="html-run")
    store.add_event(run_id, 1, "llm_call", request={"messages": []}, response={"ok": True})

    out = tmp_path / "report.html"
    write_report(run_id, out, fmt="html", store=store)

    assert out.exists()
    assert "<!doctype html>" in out.read_text(encoding="utf-8")


def test_report_includes_evidence_notes_verification_and_environment(tmp_path):
    store = RecordStore(tmp_path / "recordings.db")
    run_id = store.create_run(name="evidence-run")
    store.add_event(run_id, 1, "llm_call", request={"messages": []}, response={"ok": True})

    report = build_report(
        run_id,
        store,
        notes=["Compared against the failing run from CI."],
        verification=["pytest tests/test_agent.py -q"],
        environment={"repo": "demo-agent", "api_key": "secretvalue123456789"},
    )
    text = render_markdown(report)

    assert "Compared against the failing run from CI." in text
    assert "`pytest tests/test_agent.py -q`" in text
    assert "repo: `demo-agent`" in text
    assert "secretvalue" not in text
    assert "<REDACTED>" in text
    assert "python:" in text
    assert "platform:" in text


def test_parse_environment_items_requires_key_value():
    assert parse_environment_items(("os=windows", "node=24")) == {
        "os": "windows",
        "node": "24",
    }

    try:
        parse_environment_items(("broken",))
    except ValueError as exc:
        assert "KEY=VALUE" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_audit_reports_locations_without_secret_values(tmp_path):
    store = RecordStore(tmp_path / "recordings.db")
    run_id = store.create_run(name="audit-run")
    store.add_event(
        run_id,
        1,
        "llm_call",
        request={"headers": {"Authorization": "Bearer tokenvalue123456789"}},
        response={"content": "ok"},
    )

    findings = audit_run(run_id, store)
    text = render_audit_markdown(run_id, findings)

    assert findings
    assert findings[0].field == "request"
    assert "tokenvalue" not in text
    assert "<REDACTED>" in text
    assert all("tokenvalue" not in item.preview for item in findings)


def test_write_audit_json(tmp_path):
    store = RecordStore(tmp_path / "recordings.db")
    run_id = store.create_run(name="json-audit")
    store.add_event(run_id, 1, "llm_call", error="api_key=secretvalue123456")

    out = tmp_path / "audit.json"
    write_audit(run_id, out, fmt="json", store=store)

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload[0]["pattern"] == "api-key-field"
    assert "secretvalue" not in payload[0]["preview"]
