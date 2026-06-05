from click.testing import CliRunner

from flightbox.cli import cli


def test_audit_missing_run_reports_not_found(tmp_path):
    db = tmp_path / "recordings.db"
    result = CliRunner().invoke(cli, ["--db", str(db), "audit", "missing"])

    assert result.exit_code == 0
    assert "not found" in result.output
