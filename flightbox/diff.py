"""Diff two recorded runs to find where they diverged."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from flightbox.store import RecordStore


@dataclass
class DiffEntry:
    seq: int
    field: str
    run_a_value: Any
    run_b_value: Any


def diff_runs(
    run_a: str,
    run_b: str,
    store: RecordStore | None = None,
) -> list[DiffEntry]:
    """Compare two recorded runs event-by-event.

    Returns a list of differences. Only compares events that exist in both
    runs (by sequence number). Extra events in the longer run are reported
    as "missing" diffs.
    """
    store = store or RecordStore()
    events_a = store.get_events(run_a)
    events_b = store.get_events(run_b)

    diffs: list[DiffEntry] = []
    compare_fields = ("event_type", "provider", "model", "request", "response", "error")

    max_seq = max(len(events_a), len(events_b))
    for i in range(max_seq):
        if i >= len(events_a):
            diffs.append(DiffEntry(seq=i + 1, field="event", run_a_value=None, run_b_value="present"))
            continue
        if i >= len(events_b):
            diffs.append(DiffEntry(seq=i + 1, field="event", run_a_value="present", run_b_value=None))
            continue

        ea, eb = events_a[i], events_b[i]
        for field in compare_fields:
            va = _parse_json(ea.get(field))
            vb = _parse_json(eb.get(field))
            if va != vb:
                diffs.append(DiffEntry(seq=i + 1, field=field, run_a_value=va, run_b_value=vb))

    return diffs


def _parse_json(val: Any) -> Any:
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            pass
    return val
