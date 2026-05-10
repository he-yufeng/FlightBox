# FlightBox

**Black-box flight recorder for AI agents** — record every LLM call your agent makes, then replay sessions deterministically to reproduce bugs.

Like an airplane's black box, but for your AI agent. Zero cloud dependency, pure local SQLite.

## Why?

Your agent broke in production. The user reports "it gave a weird answer." You have no idea what happened because:

- The LLM response was non-deterministic
- You can't replay the exact sequence of calls
- The logs only show the final output, not the intermediate steps

FlightBox fixes this. Wrap your code with `flightbox.record()`, and every LLM call is captured with full request/response pairs, latency, token usage, and tool calls. Later, use `flightbox.replay()` to feed the exact same responses back to your agent — making it fully deterministic for debugging.

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

Every `client.chat.completions.create()` call within the block is automatically captured — no code changes needed beyond the `with` block.

### Replay

```python
import flightbox

with flightbox.replay("abc123def4") as ctx:
    # Same agent code, but LLM calls return recorded responses
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "What is 2+2?"}],
    )
    # response is the exact same as the original recording
    print(response.choices[0].message.content)  # "4"
```

### Diff Two Runs

```bash
flightbox diff <run-a> <run-b>
```

Shows exactly where two runs diverged — which step, which field (request, response, model) changed.

### Export as Eval Dataset

```bash
# JSONL format (one line per LLM call, with messages + expected response)
flightbox export <run-id> -f jsonl -o eval_dataset.jsonl

# Or generate a pytest replay test
flightbox export <run-id> -f pytest -o test_replay.py
```

### LiteLLM

FlightBox can record and replay LiteLLM calls too:

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
    response = litellm.completion(
        model="openrouter/openai/gpt-4o-mini",
        messages=[{"role": "user", "content": "ping"}],
    )
```

## CLI Reference

```bash
flightbox list                    # List all recorded runs
flightbox show <run-id>           # Show run details and events
flightbox diff <run-a> <run-b>    # Compare two runs
flightbox export <run-id>         # Export as JSONL or pytest
flightbox delete <run-id>         # Delete a recording
```

## How It Works

FlightBox monkey-patches the OpenAI and Anthropic Python SDKs to intercept `chat.completions.create()` and `messages.create()` calls. All data is stored in a local SQLite database (`.flightbox/recordings.db` by default).

During replay, the patched methods return saved responses instead of making real API calls — making your agent fully deterministic.

**Supported SDKs:**
- OpenAI Python SDK (`openai>=1.0`) — sync and async
- Anthropic Python SDK (`anthropic>=0.20`)
- LiteLLM (`litellm>=1.0`) — `completion` and `acompletion`
- Any SDK that wraps these (LangChain, CrewAI, Pydantic AI, etc.)

## Storage

Recordings are stored in `.flightbox/recordings.db` (SQLite). You can customize the path:

```python
from flightbox import RecordStore

store = RecordStore("path/to/my/recordings.db")
with flightbox.record("test", store=store) as rec:
    ...
```

## Use Cases

- **Bug reproduction**: Record production agent runs, replay locally to debug
- **Regression testing**: Export runs as eval datasets, test that agent behavior doesn't change after code updates
- **Cost analysis**: See token usage breakdown per LLM call in a session
- **Team collaboration**: Share `.flightbox/recordings.db` with teammates so they can replay and investigate

## License

MIT

---

# FlightBox

**AI Agent 黑匣子** — 记录 Agent 的每一次 LLM 调用，然后确定性地回放来复现 Bug。

就像飞机的黑匣子，但给 AI Agent 用。纯本地 SQLite，零云依赖。

## 为什么需要？

Agent 在生产环境出了 bug，用户说"它给了个奇怪的回答"。你没法复现，因为：

- LLM 响应是非确定性的
- 你无法重放完全相同的调用序列
- 日志只有最终输出，没有中间步骤

FlightBox 解决这个问题。用 `flightbox.record()` 包裹你的代码，每次 LLM 调用的完整请求/响应、延迟、token 用量都会被记录。之后用 `flightbox.replay()` 把录制的响应原样喂回给 Agent，实现完全确定性的调试。

## 快速开始

```bash
pip install flightbox
```

### 录制

```python
import flightbox
from openai import OpenAI

client = OpenAI()

with flightbox.record("debug-session") as rec:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "2+2等于多少？"}],
    )
    print(response.choices[0].message.content)

print(f"录制 ID: {rec.run_id}")
```

### 回放

```python
with flightbox.replay("abc123def4") as ctx:
    # 同样的 Agent 代码，但 LLM 调用返回录制的响应
    response = client.chat.completions.create(...)
    # response 和原始录制完全一致
```

### 对比两次运行

```bash
flightbox diff <run-a> <run-b>
```

### 导出为评测数据集

```bash
flightbox export <run-id> -f jsonl -o eval.jsonl
flightbox export <run-id> -f pytest -o test_replay.py
```

## 支持的 SDK

- OpenAI Python SDK（同步 + 异步）
- Anthropic Python SDK
- LiteLLM（`completion` + `acompletion`）
- 任何基于这些 SDK 的框架（LangChain、CrewAI、Pydantic AI 等）

## License

MIT
