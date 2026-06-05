"""Secret audit helpers for recorded FlightBox runs."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from flightbox.store import RecordStore

_PATTERNS = {
    "openai-style-key": re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    "github-token": re.compile(r"(?:gho|ghp|github_pat)_[A-Za-z0-9_]{20,}"),
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
    pattern: str
    preview: str


def audit_run(run_id: str, store: RecordStore | None = None) -> list[AuditFinding]:
    owns_store = store is None
    store = store or RecordStore()
    findings: list[AuditFinding] = []
    try:
        for event in store.get_events(run_id):
            seq = int(event["seq"])
            for field in ("request", "response", "token_usage", "error"):
                value = event.get(field)
                if value in (None, ""):
                    continue
                findings.extend(_scan_value(seq, field, _loads(value)))
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

    lines.append("| Event | Field | Pattern | Redacted preview |")
    lines.append("|---:|---|---|---|")
    for item in findings:
        lines.append(
            f"| {item.seq} | `{item.field}` | `{item.pattern}` | `{item.preview}` |"
        )
    lines.append("")
    return "\n".join(lines)


def write_audit(
    run_id: str,
    output: str | Path,
    *,
    fmt: str = "md",
    store: RecordStore | None = None,
) -> Path:
    findings = audit_run(run_id, store)
    out = Path(output)
    if fmt == "json":
        out.write_text(
            json.dumps([asdict(item) for item in findings], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    else:
        out.write_text(render_audit_markdown(run_id, findings), encoding="utf-8")
    return out


def _scan_value(seq: int, field: str, value: Any) -> list[AuditFinding]:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value
    findings: list[AuditFinding] = []
    for name, pattern in _PATTERNS.items():
        for match in pattern.finditer(text):
            findings.append(
                AuditFinding(
                    seq=seq,
                    field=field,
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
