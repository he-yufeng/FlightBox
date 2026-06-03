<p align="right"><a href="README_CN.md">中文文档</a></p>

# FlightBox

**Black-box flight recorder for AI agents** — record every LLM call your agent makes, replay sessions deterministically, and export a redacted evidence report when something breaks.

FlightBox is local-first. Recordings live in SQLite. No hosted dashboard is required.

## Why

An agent failed and nobody can reproduce it. The final answer is in a log, but the interesting evidence is scattered across LLM requests, tool calls, model responses, timing, tokens, and local notes.

FlightBox gives you a deterministic debugging trail:

- record OpenAI / Anthropic / LiteLLM calls
- replay the same responses later
- diff two runs
- export JSONL or pytest replay tests
- generate a redacted Markdown / HTML report for PRs, CI notes, and teammates

## Quick Start

```bash
pip install flightbox
```

### Record

```python
import flightbox
from openai import OpenAI

client = OpenAI()

with flightbox.record("debug-session") as rec:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "What is 2+2?"}],
    )
    print(response.choices[0].message.content)

print(f"Recorded as run: {rec.run_id}")
```

### Replay

```python
import flightbox

with flightbox.replay("abc123def4"):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "What is 2+2?"}],
    )
    print(response.choices[0].message.content)
```

### Inspect

```bash
flightbox list
flightbox show <run-id>
flightbox stats <run-id>
flightbox diff <run-a> <run-b>
```

### Export

```bash
# JSONL eval rows
flightbox export <run-id> -f jsonl -o eval_dataset.jsonl

# pytest replay skeleton
flightbox export <run-id> -f pytest -o test_replay.py

# redacted evidence report
flightbox report <run-id> -f md -o evidence.md
flightbox report <run-id> -f html -o evidence.html
```

The report redacts common API keys, bearer tokens, GitHub tokens, and authorization headers before writing the file.

## LiteLLM

```bash
pip install "flightbox[litellm]"
```

```python
import flightbox
import litellm

with flightbox.record("router-debug") as rec:
    litellm.completion(
        model="openrouter/openai/gpt-4o-mini",
        messages=[{"role": "user", "content": "ping"}],
    )

with flightbox.replay(rec.run_id):
    litellm.completion(
        model="openrouter/openai/gpt-4o-mini",
        messages=[{"role": "user", "content": "ping"}],
    )
```

## CLI Reference

```bash
flightbox list                    # List recorded runs
flightbox show <run-id>           # Show run details and events
flightbox stats <run-id>          # Summarize latency, tokens, and errors
flightbox diff <run-a> <run-b>    # Compare two runs
flightbox export <run-id>         # Export as JSONL or pytest
flightbox report <run-id>         # Export a redacted evidence report
flightbox delete <run-id>         # Delete a recording
```

## Supported SDKs

- OpenAI Python SDK (`openai>=1.0`) — sync and async
- Anthropic Python SDK (`anthropic>=0.20`)
- LiteLLM (`litellm>=1.0`) — `completion` and `acompletion`
- SDKs and frameworks that call through those clients

## Storage

Recordings are stored in `.flightbox/recordings.db` by default. You can pass a custom database path with `--db` in the CLI or by constructing `RecordStore` yourself.

## License

MIT
