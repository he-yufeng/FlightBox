"""Secret audit helpers for recorded FlightBox runs."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from flightbox.store import RecordStore

_PATTERNS = {
    "openai-style-key": re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    "github-token": re.compile(r"(?:gho|ghp|github_pat)_[A-Za-z0-9_]{20,}"),
    "aws-access-key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "google-api-key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "slack-token": re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"),
    "pem-private-key": re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"
    ),
    "bearer-token": re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    "api-key-field": re.compile(r"(?i)api[_-]?key['\"]?\s*[:=]\s*['\"]?[^'\"\s,}]+"),
    "authorization-field": re.compile(
        r"(?i)authorization['\"]?\s*[:=]\s*['\"]?(?:bearer\s+)?[A-Za-z0-9._~+/=-]{8,}"
    ),
}


@dataclass(frozen=True)
class AuditFinding:
    seq: int
    field: str
    path: str
    pattern: str
    preview: str


@dataclass(frozen=True)
class AuditPolicy:
    ignored_fields: tuple[str, ...] = ()
    ignored_paths: tuple[str, ...] = ()
    disabled_patterns: tuple[str, ...] = ()

    def ignores_field(self, field: str) -> bool:
        return field in self.ignored_fields

    def ignores_path(self, path: str) -> bool:
        return any(fnmatchcase(path, pattern) for pattern in self.ignored_paths)

    def disables_pattern(self, pattern: str) -> bool:
        return pattern in self.disabled_patterns


def load_audit_policy(path: str | Path | None = None) -> AuditPolicy:
    policy_path = Path(path) if path else Path(".flightboxignore")
    if not policy_path.exists():
        return AuditPolicy()

    fields: list[str] = []
    paths: list[str] = []
    patterns: list[str] = []
    for raw in policy_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            paths.append(line)
            continue
        kind, value = (part.strip() for part in line.split(":", 1))
        if kind == "field":
            fields.append(value)
        elif kind == "path":
            paths.append(value)
        elif kind == "pattern":
            patterns.append(value)
        else:
            paths.append(line)
    return AuditPolicy(tuple(fields), tuple(paths), tuple(patterns))


def audit_run(
    run_id: str,
    store: RecordStore | None = None,
    *,
    policy: AuditPolicy | None = None,
    policy_path: str | Path | None = None,
) -> list[AuditFinding]:
    owns_store = store is None
    store = store or RecordStore()
    policy = policy or load_audit_policy(policy_path)
    findings: list[AuditFinding] = []
    try:
        for event in store.get_events(run_id):
            seq = int(event["seq"])
            for field in ("request", "response", "token_usage", "error"):
                if policy.ignores_field(field):
                    continue
                value = event.get(field)
                if value in (None, ""):
                    continue
                findings.extend(_scan_value(seq, field, field, _loads(value), policy))
    finally:
        if owns_store:
            store.close()
    return findings


def render_audit_markdown(run_id: str, findings: list[AuditFinding]) -> str:
    lines = [
        f"# FlightBox Secret Audit: {run_id}",
        "",
        "This audit scans the raw recording for common token patterns. It reports",
        "where a possible secret appeared, but never prints the original value.",
        "",
    ]
    if not findings:
        lines.append("No common secret patterns were found in the recorded payloads.")
        lines.append("")
        return "\n".join(lines)

    lines.append("| Event | Field | Path | Pattern | Redacted preview |")
    lines.append("|---:|---|---|---|---|")
    for item in findings:
        lines.append(
            f"| {item.seq} | `{item.field}` | `{item.path}` | `{item.pattern}` | `{item.preview}` |"
        )
    lines.append("")
    return "\n".join(lines)


def write_audit(
    run_id: str,
    output: str | Path,
    *,
    fmt: str = "md",
    store: RecordStore | None = None,
    policy_path: str | Path | None = None,
) -> Path:
    findings = audit_run(run_id, store, policy_path=policy_path)
    out = Path(output)
    if fmt == "json":
        out.write_text(
            json.dumps([asdict(item) for item in findings], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    else:
        out.write_text(render_audit_markdown(run_id, findings), encoding="utf-8")
    return out


def _scan_value(
    seq: int,
    field: str,
    path: str,
    value: Any,
    policy: AuditPolicy,
) -> list[AuditFinding]:
    if policy.ignores_path(path):
        return []
    if isinstance(value, dict):
        findings: list[AuditFinding] = []
        for key, child in value.items():
            findings.extend(_scan_value(seq, field, f"{path}.{key}", child, policy))
        return findings
    if isinstance(value, list):
        findings = []
        for child in value:
            findings.extend(_scan_value(seq, field, f"{path}.*", child, policy))
        return findings

    text = json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value
    findings: list[AuditFinding] = []
    for name, pattern in _PATTERNS.items():
        if policy.disables_pattern(name):
            continue
        for match in pattern.finditer(text):
            findings.append(
                AuditFinding(
                    seq=seq,
                    field=field,
                    path=path,
                    pattern=name,
                    preview=_preview(text, match.start(), match.end()),
                )
            )
    return findings


def _loads(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _preview(text: str, start: int, end: int) -> str:
    left = text[max(0, start - 24) : start]
    right = text[end : end + 24]
    return f"{_one_line(left)}<REDACTED>{_one_line(right)}"


def _one_line(value: str) -> str:
    return " ".join(value.replace("|", "\\|").split())
