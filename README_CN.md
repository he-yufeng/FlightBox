<div align="center">

<img src="docs/banner.png" alt="FlightBox — 记录、回放、对比 Agent 每一次 LLM 调用" width="100%">

[![PyPI](https://img.shields.io/pypi/v/flightbox.svg)](https://pypi.org/project/flightbox/)
[![Python](https://img.shields.io/pypi/pyversions/flightbox.svg)](https://pypi.org/project/flightbox/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[**快速开始**](#快速开始) · [**录制**](#录制) · [**回放**](#回放) · [**对比**](#diff) · [English](README.md)

</div>

<p align="center"><img src="docs/demo.png" alt="flightbox record and replay" width="620"></p>

**AI Agent 调试黑匣子**：记录 Agent 的每一次 LLM 调用，之后可以确定性回放、对比两次运行，并导出脱敏后的证据报告。

Agent 出错时，最难的不是“知道它错了”，而是复现它为什么错。一次失败通常散落在 LLM 请求、模型回复、工具调用、stdout、测试命令、CI 日志和 PR 评论里。FlightBox 先把 LLM 调用链记录下来，再把它变成可回放、可对比、可分享的证据。

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
        messages=[{"role": "user", "content": "2+2 等于多少？"}],
    )
    print(response.choices[0].message.content)

print(f"录制 ID: {rec.run_id}")
```

### 回放

```python
with flightbox.replay("abc123def4"):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "2+2 等于多少？"}],
    )
```

### 生成证据报告

```bash
flightbox report <run-id> -f md -o evidence.md
flightbox report <run-id> -f html -o evidence.html
flightbox report <run-id> \
  --note "修复 retry path 后复现通过" \
  --verify "pytest tests/test_agent.py -q" \
  --env repo=agent-demo \
  -o evidence.md
flightbox timeline <run-id> -o timeline.md
flightbox audit <run-id>
flightbox audit <run-id> --policy .flightboxignore
```

报告会在写出前脱敏常见 API key、Bearer token、GitHub token 和 Authorization header，适合贴到 PR、issue、CI 复盘或者发给同事。报告现在也会附带轻量证据信息：备注、验证命令、Python 版本、平台信息，以及你手动传入的 `KEY=VALUE` 环境事实。

如果只想快速看一次运行的关键调用链，可以用 `timeline`。它会按调用顺序输出一张 Markdown 表，包含 provider、model、耗时、token、错误状态，以及脱敏后的请求 / 回复摘要。这个格式比完整报告更短，适合放在 PR 评论、debug 记录或 issue 复盘里。

分享证据前可以先跑 `audit`。它扫描原始 recording 里是否有常见 token / API key 模式，但只输出事件编号、顶层字段、JSON 路径、命中类型和脱敏预览，不回显真实 secret。如果某些字段里本来就会出现安全的示例 token，可以用 `.flightboxignore` 控制误报：

```text
# 忽略整个顶层字段
field:token_usage

# 忽略某个 JSON 路径，* 表示列表元素
path:request.messages.*.content

# 关闭某类 pattern
pattern:github-token
```

## 常用命令

```bash
flightbox list
flightbox show <run-id>
flightbox stats <run-id>
flightbox diff <run-a> <run-b>
flightbox diff <run-a> <run-b> --ignore-field request
flightbox timeline <run-id> -o timeline.md
flightbox audit <run-id>
flightbox audit <run-id> --policy .flightboxignore
flightbox export <run-id> -f jsonl -o eval_dataset.jsonl
flightbox export <run-id> -f jsonl --raw -o private_fixture.jsonl
flightbox export <run-id> -f pytest -o test_replay.py
flightbox report <run-id> -f md -o evidence.md
flightbox report <run-id> --note "..." --verify "pytest -q" --env os=windows
```

## 适合什么场景

- Agent 生产问题复现
- LLM 调用链审计
- 对比两次 agent run 的分叉点
- 把真实运行记录转成默认脱敏的 eval dataset；只有私有 fixture 才用 `--raw`
- 给 PR / CI / review 准备脱敏证据包

## 支持范围

- OpenAI Python SDK
- Anthropic Python SDK
- LiteLLM
- 调用这些 SDK 的上层 Agent 框架

FlightBox 不依赖云端服务，不需要把你的调试数据上传到第三方平台。录制默认保存在本地 `.flightbox/recordings.db`。

## 后续规划

录制、回放、对比、报告这条主线已经稳定，接下来想覆盖 Agent 实际会调用的更多东西，并把 recording 变成真正能拦回归的关卡：

- **更广的 SDK 支持**：Google GenAI、Cohere、以及裸 HTTP 的 LLM 客户端，让一次录制不再取决于 Agent 恰好用了哪个 SDK。
- **CI 里的基线断言**：`flightbox assert <run> --against baseline.jsonl`，当 Agent 的调用序列偏离录好的基线时让构建失败，把行为变化挡在评审阶段而不是上线之后。
- **成本与耗时趋势**：把已经记录的每次调用 token / 耗时汇总成一张跨运行的小表，让花费回归和输出回归一样一眼可见。
- **本地 transcript 查看器**：把一次运行的调用链渲染成单文件 HTML，当 Markdown timeline 还不足以看清两次运行从哪里分叉时用。

整条路线都坚持本地优先，任何 recording 都不必离开你的机器。

## License

MIT
