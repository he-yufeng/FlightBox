"""The audit scanner must flag the same cloud-provider secrets the report redacts."""

from flightbox.audit import audit_run, load_audit_policy
from flightbox.store import RecordStore

# Assemble the secret-shaped values at runtime so the literals never sit in the
# source verbatim — committing them as-is would trip secret-scanning push rules.
_AWS = "AKIA" + "1234567890ABCDEF"
_GOOGLE = "AIza" + "B" * 35
_SLACK = "xoxb-" + "1234567890" + "-abcdefghijklmnop"
_PEM = (
    "-----BEGIN RSA " + "PRIVATE KEY-----"
    "\nFAKEKEYMATERIAL1234567890abcdef\n"
    "-----END RSA " + "PRIVATE KEY-----"
)


def _run_with_secrets(tmp_path):
    store = RecordStore(tmp_path / "recordings.db")
    run_id = store.create_run(name="cloud-keys")
    store.add_event(
        run_id,
        1,
        "llm_call",
        request={"aws": _AWS, "google": _GOOGLE},
        response={"slack": _SLACK, "pem": _PEM},
    )
    return store, run_id


def test_audit_flags_cloud_provider_and_pem_secrets(tmp_path):
    store, run_id = _run_with_secrets(tmp_path)
    patterns = {f.pattern for f in audit_run(run_id, store)}
    assert "aws-access-key" in patterns
    assert "google-api-key" in patterns
    assert "slack-token" in patterns
    assert "pem-private-key" in patterns


def test_audit_policy_can_disable_a_cloud_key_pattern(tmp_path):
    store, run_id = _run_with_secrets(tmp_path)
    policy_path = tmp_path / ".flightboxignore"
    policy_path.write_text("pattern:aws-access-key\n", encoding="utf-8")
    policy = load_audit_policy(policy_path)
    patterns = {f.pattern for f in audit_run(run_id, store, policy=policy)}
    assert "aws-access-key" not in patterns
    # the others are still flagged
    assert "google-api-key" in patterns
