import json

from flightbox.audit import audit_run, load_audit_policy, write_audit
from flightbox.store import RecordStore


def test_audit_policy_ignores_paths_and_patterns(tmp_path):
    fake_github_token = "ghp_" + ("a" * 26)
    policy_path = tmp_path / ".flightboxignore"
    policy_path.write_text(
        "\n".join(
            [
                "path:request.messages.*.content",
                "pattern:github-token",
            ]
        ),
        encoding="utf-8",
    )
    store = RecordStore(tmp_path / "recordings.db")
    run_id = store.create_run(name="policy-run")
    store.add_event(
        run_id,
        1,
        "llm_call",
        request={"messages": [{"content": "Authorization: Bearer tokenvalue123456789"}]},
        response={"token": fake_github_token},
        error="api_key=secretvalue123456",
    )

    findings = audit_run(run_id, store, policy_path=policy_path)

    assert [item.pattern for item in findings] == ["api-key-field"]
    assert findings[0].path == "error"


def test_write_audit_json_includes_json_path(tmp_path):
    store = RecordStore(tmp_path / "recordings.db")
    run_id = store.create_run(name="path-run")
    store.add_event(
        run_id,
        1,
        "llm_call",
        request={"headers": {"Authorization": "Bearer tokenvalue123456789"}},
    )

    out = tmp_path / "audit.json"
    write_audit(run_id, out, fmt="json", store=store)

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload[0]["field"] == "request"
    assert payload[0]["path"] == "request.headers.Authorization"


def test_load_audit_policy_accepts_field_path_and_pattern(tmp_path):
    policy_path = tmp_path / ".flightboxignore"
    policy_path.write_text(
        "field:token_usage\npath:request.debug\npattern:bearer-token\n",
        encoding="utf-8",
    )

    policy = load_audit_policy(policy_path)

    assert policy.ignores_field("token_usage")
    assert policy.ignores_path("request.debug")
    assert policy.disables_pattern("bearer-token")
