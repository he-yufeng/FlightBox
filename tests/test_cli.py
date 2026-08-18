from click.testing import CliRunner

from flightbox.cli import cli
from flightbox.store import RecordStore


def test_audit_missing_run_reports_not_found(tmp_path):
    db = tmp_path / "recordings.db"
    result = CliRunner().invoke(cli, ["--db", str(db), "audit", "missing"])

    assert result.exit_code == 0
    assert "not found" in result.output


def test_report_cli_accepts_evidence_options(tmp_path):
    db = tmp_path / "recordings.db"
    store = RecordStore(db)
    run_id = store.create_run(name="cli-report")
    store.add_event(run_id, 1, "llm_call", request={"messages": []}, response={"ok": True})
    store.close()

    out = tmp_path / "report.md"
    result = CliRunner().invoke(
        cli,
        [
            "--db",
            str(db),
            "report",
            run_id,
            "--note",
            "reviewed retry path",
            "--verify",
            "pytest -q",
            "--env",
            "os=windows",
            "--output",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    assert "reviewed retry path" in text
    assert "`pytest -q`" in text
    assert "os: `windows`" in text


def test_report_cli_rejects_bad_environment_item(tmp_path):
    db = tmp_path / "recordings.db"
    result = CliRunner().invoke(
        cli,
        ["--db", str(db), "report", "missing", "--env", "broken"],
    )

    assert result.exit_code != 0
    assert "KEY=VALUE" in result.output


def test_diff_cli_can_ignore_noisy_fields(tmp_path):
    db = tmp_path / "recordings.db"
    store = RecordStore(db)
    run_a = store.create_run(name="a")
    run_b = store.create_run(name="b")
    store.add_event(run_a, 1, "llm_call", request={"trace": "a"}, response={"text": "ok"})
    store.add_event(run_b, 1, "llm_call", request={"trace": "b"}, response={"text": "ok"})
    store.close()

    result = CliRunner().invoke(
        cli,
        ["--db", str(db), "diff", run_a, run_b, "--ignore-field", "request"],
    )

    assert result.exit_code == 0, result.output
    assert "Runs are identical" in result.output


def _seed_run_with_secret(db):
    store = RecordStore(db)
    run_id = store.create_run(name="leaky")
    store.add_event(
        run_id,
        1,
        "llm_call",
        request={"messages": [{"content": "hi"}]},
        response={"ok": True},
        error="api_key=secretvalue123456",
    )
    store.close()
    return run_id


def test_audit_strict_exits_nonzero_on_findings(tmp_path):
    db = tmp_path / "recordings.db"
    run_id = _seed_run_with_secret(db)

    result = CliRunner().invoke(cli, ["--db", str(db), "audit", run_id, "--strict"])

    assert result.exit_code == 1
    assert "api-key-field" in result.output


def test_audit_strict_clean_run_exits_zero(tmp_path):
    db = tmp_path / "recordings.db"
    store = RecordStore(db)
    run_id = store.create_run(name="clean")
    store.add_event(run_id, 1, "llm_call", request={"messages": []}, response={"ok": True})
    store.close()

    result = CliRunner().invoke(cli, ["--db", str(db), "audit", run_id, "--strict"])

    assert result.exit_code == 0
    assert "No common secret patterns" in result.output


def test_audit_strict_still_writes_report_before_exiting(tmp_path):
    db = tmp_path / "recordings.db"
    run_id = _seed_run_with_secret(db)
    out = tmp_path / "audit.md"

    result = CliRunner().invoke(
        cli, ["--db", str(db), "audit", run_id, "--strict", "--output", str(out)]
    )

    assert result.exit_code == 1
    assert out.exists()
    assert "api-key-field" in out.read_text(encoding="utf-8")
