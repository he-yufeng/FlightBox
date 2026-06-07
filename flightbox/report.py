"""Generate shareable reports for recorded runs."""

from __future__ import annotations

import html
import json
import platform
import re
import sys
from pathlib import Path
from typing import Any

from flightbox.store import RecordStore

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"(gho|ghp|github_pat)_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)(api[_-]?key['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+"),
    re.compile(r"(?i)(authorization['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+"),
]


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "<REDACTED>" if _is_secret_key(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        redacted = value
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(_replace_secret, redacted)
        return redacted
    return value


def _is_secret_key(key: str) -> bool:
    key = key.lower()
    return any(
        marker in key
        for marker in ("api_key", "apikey", "authorization", "access_token", "secret", "password")
    )


def build_report(
    run_id: str,
    store: RecordStore | None = None,
    *,
    notes: list[str] | None = None,
    verification: list[str] | None = None,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    store = store or RecordStore()
    run = store.get_run(run_id)
    if not run:
        raise ValueError(f"Run not found: {run_id}")

    stats = store.get_run_stats(run_id)
    events = []
    for event in store.get_events(run_id):
        events.append(
            {
                "seq": event["seq"],
                "timestamp": event["timestamp"],
                "event_type": event["event_type"],
                "provider": event.get("provider"),
                "model": event.get("model"),
                "latency_ms": event.get("latency_ms"),
                "token_usage": redact(_loads(event.get("token_usage"))),
                "error": redact(event.get("error") or ""),
                "request": redact(_loads(event.get("request"))),
                "response": redact(_loads(event.get("response"))),
            }
        )

    return {
        "run": redact(run),
        "stats": stats,
        "events": events,
        "evidence": {
            "notes": notes or [],
            "verification": verification or [],
            "environment": _report_environment(environment),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    run = report["run"]
    stats = report["stats"]
    evidence = report.get("evidence") or {}
    notes = evidence.get("notes") or []
    verification = evidence.get("verification") or []
    environment = evidence.get("environment") or {}
    lines = [
        f"# FlightBox Report: {run['run_id']}",
        "",
        f"- Name: `{run.get('name') or '-'}`",
        f"- Started: `{run.get('started_at')}`",
        f"- Finished: `{run.get('finished_at') or 'in progress'}`",
        f"- Events: `{stats['events']}`",
        f"- LLM calls: `{stats['llm_calls']}`",
        f"- Errors: `{stats['errors']}`",
        f"- Total tokens: `{stats['total_tokens']}`",
        f"- Total latency: `{stats['latency_ms_total']:.0f}ms`",
        "",
        "## Evidence Notes",
        "",
    ]
    if notes:
        lines.extend(f"- {note}" for note in notes)
    else:
        lines.append("- No extra notes supplied.")

    lines.extend(["", "## Verification", ""])
    if verification:
        lines.extend(f"- `{command}`" for command in verification)
    else:
        lines.append("- No verification commands supplied.")

    lines.extend(["", "## Environment", ""])
    if environment:
        for key, value in environment.items():
            lines.append(f"- {key}: `{value}`")
    else:
        lines.append("- No environment metadata.")

    lines.extend(
        [
            "",
            "## Timeline",
            "",
            "| # | Type | Provider | Model | Latency | Error |",
            "| ---: | --- | --- | --- | ---: | --- |",
        ]
    )
    for event in report["events"]:
        lines.append(
            "| "
            f"{event['seq']} | {event['event_type']} | {event.get('provider') or '-'} | "
            f"{event.get('model') or '-'} | {_fmt_latency(event.get('latency_ms'))} | "
            f"{_one_line(event.get('error') or '-')} |"
        )

    lines.extend(["", "## Event Details", ""])
    for event in report["events"]:
        lines.extend(
            [
                f"### Event {event['seq']}: {event['event_type']}",
                "",
                "Request:",
                "```json",
                json.dumps(event["request"], indent=2, ensure_ascii=False),
                "```",
                "",
                "Response:",
                "```json",
                json.dumps(event["response"], indent=2, ensure_ascii=False),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_html(report: dict[str, Any]) -> str:
    markdown = render_markdown(report)
    return f"""<!doctype html>
<meta charset="utf-8">
<title>FlightBox Report {html.escape(report['run']['run_id'])}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 980px; margin: 40px auto; line-height: 1.5; }}
pre {{ background: #f6f8fa; padding: 12px; border-radius: 6px; overflow: auto; }}
code {{ background: #f6f8fa; border-radius: 4px; padding: 1px 4px; }}
</style>
<pre>{html.escape(markdown)}</pre>
"""


def write_report(
    run_id: str,
    output: str | Path,
    *,
    fmt: str = "md",
    store: RecordStore | None = None,
    notes: list[str] | None = None,
    verification: list[str] | None = None,
    environment: dict[str, str] | None = None,
) -> Path:
    report = build_report(
        run_id,
        store,
        notes=notes,
        verification=verification,
        environment=environment,
    )
    text = render_html(report) if fmt == "html" else render_markdown(report)
    out = Path(output)
    out.write_text(text, encoding="utf-8")
    return out


def parse_environment_items(items: list[str] | tuple[str, ...]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"environment item must be KEY=VALUE: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"environment item must have a key: {item}")
        parsed[key] = value.strip()
    return parsed


def _report_environment(extra: dict[str, str] | None) -> dict[str, str]:
    data = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }
    if extra:
        data.update(redact(extra))
    return data


def _loads(value: Any) -> Any:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _replace_secret(match: re.Match[str]) -> str:
    if match.lastindex:
        return f"{match.group(1)}<REDACTED>"
    return "<REDACTED>"


def _fmt_latency(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.0f}ms"


def _one_line(value: str) -> str:
    return value.replace("\n", " ")[:120]
