"""Export recorded sessions as test cases or eval datasets."""

from __future__ import annotations

import json
from pathlib import Path

from flightbox.store import RecordStore


def export_jsonl(
    run_id: str,
    output: str | Path,
    store: RecordStore | None = None,
) -> int:
    """Export a run's LLM calls as a JSONL file (one line per call).

    Each line contains: {"messages": [...], "expected_response": {...}, "model": "..."}
    Useful for building eval datasets from production traces.
    """
    store = store or RecordStore()
    events = store.get_events(run_id)
    output = Path(output)
    count = 0

    with output.open("w") as f:
        for ev in events:
            if ev["event_type"] != "llm_call":
                continue
            req = json.loads(ev["request"]) if isinstance(ev["request"], str) else ev["request"]
            resp = json.loads(ev["response"]) if isinstance(ev["response"], str) else ev["response"]
            if not req or not resp:
                continue

            entry = {
                "messages": req.get("messages", []),
                "model": ev.get("model"),
                "expected_response": resp,
            }
            if req.get("tools"):
                entry["tools"] = req["tools"]

            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            count += 1

    return count


def export_pytest(
    run_id: str,
    output: str | Path,
    store: RecordStore | None = None,
) -> int:
    """Export a run as a pytest test file that replays the session.

    The generated test uses flightbox.replay() to deterministically
    re-execute the recorded LLM calls and verify the responses match.
    """
    store = store or RecordStore()
    run = store.get_run(run_id)
    event_count = store.get_event_count(run_id)
    output = Path(output)

    name = run.get("name", run_id) if run else run_id
    safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in str(name))

    code = f'''"""Auto-generated replay test for run '{name}'."""
import flightbox


def test_replay_{safe_name}():
    """Replay run {run_id} and verify it completes without error."""
    with flightbox.replay("{run_id}") as ctx:
        # TODO: add your agent invocation here
        # result = my_agent.run("same input as original run")
        pass
    assert ctx.events_replayed == {event_count}, (
        f"Expected {event_count} events, got {{ctx.events_replayed}}"
    )
'''

    output.write_text(code)
    return event_count
