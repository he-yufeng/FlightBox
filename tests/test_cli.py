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
