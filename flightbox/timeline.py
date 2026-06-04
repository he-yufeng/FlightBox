"""Compact timelines for recorded runs."""

from __future__ import annotations

import json
from typing import Any

from flightbox.report import redact
from flightbox.store import RecordStore


def build_timeline(run_id: str, store: RecordStore | None = None) -> list[dict[str, Any]]:
    owns_store = store is None
    store = store or RecordStore()
    rows: list[dict[str, Any]] = []
    try:
        for event in store.get_events(run_id):
            usage = _loads(event.get("token_usage")) or {}
            request = redact(_loads(event.get("request")))
            response = redact(_loads(event.get("response")))
            rows.append(
                {
                    "seq": event["seq"],
                    "timestamp": event["timestamp"],
                    "type": event["event_type"],
                    "provider": event.get("provider") or "-",
                    "model": event.get("model") or "-",
                    "latency_ms": event.get("latency_ms"),
                    "tokens": _token_total(usage),
                    "error": redact(event.get("error") or ""),
                    "request_preview": _preview(request),
                    "response_preview": _preview(response),
                }
            )
    finally:
        if owns_store:
            store.close()
    return rows


def render_timeline_markdown(run_id: str, rows: list[dict[str, Any]]) -> str:
    lines = [
        f"# FlightBox Timeline: {run_id}",
        "",
        "| # | Type | Provider | Model | Latency | Tokens | Error | Request | Response |",
        "| ---: | --- | --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row['seq']} | {row['type']} | {row['provider']} | {row['model']} | "
            f"{_fmt_latency(row['latency_ms'])} | {row['tokens'] or '-'} | "
            f"{_cell(row['error'] or '-')} | {_cell(row['request_preview'])} | "
            f"{_cell(row['response_preview'])} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _loads(value: Any) -> Any:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _token_total(usage: Any) -> int:
    if not isinstance(usage, dict):
        return 0
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    return int(usage.get("total_tokens") or prompt + completion)


def _preview(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = " ".join(text.split())
    return text[:160] + ("..." if len(text) > 160 else "")


def _fmt_latency(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.0f}ms"


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")[:180]
