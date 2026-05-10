"""Replay a recorded session by serving saved responses back to the agent."""

from __future__ import annotations

import functools
import json
from typing import Any, Callable, Optional

from flightbox.store import RecordStore


class _ReplayState:
    """Holds the event queue for a replay session."""

    def __init__(self, events: list[dict]):
        self.events = events
        self.cursor = 0

    def next_response(self) -> dict | None:
        while self.cursor < len(self.events):
            ev = self.events[self.cursor]
            self.cursor += 1
            if ev["event_type"] == "llm_call" and ev["response"]:
                return ev
        return None


class ReplayContext:
    """Context manager that replays a recorded run deterministically."""

    def __init__(self, run_id: str, store: RecordStore | None = None):
        self.store = store or RecordStore()
        self.run_id = run_id
        self._state: Optional[_ReplayState] = None
        self._patches: list[tuple[Any, str, Any]] = []

    def start(self):
        events = self.store.get_events(self.run_id)
        self._state = _ReplayState(events)
        self._patch_openai()
        self._patch_anthropic()
        self._patch_litellm()

    def stop(self):
        for obj, attr, original in reversed(self._patches):
            setattr(obj, attr, original)
        self._patches.clear()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    @property
    def events_replayed(self) -> int:
        return self._state.cursor if self._state else 0

    def _build_mock_response(self, provider: str, response_data: dict) -> Any:
        """Reconstruct a response object from stored data."""
        if provider == "openai":
            try:
                from openai.types.chat import ChatCompletion
                return ChatCompletion.model_validate(response_data)
            except (ImportError, Exception):
                pass
        if provider == "anthropic":
            try:
                from anthropic.types import Message
                return Message.model_validate(response_data)
            except (ImportError, Exception):
                pass
        if provider == "litellm":
            return response_data
        # fallback: return the raw dict
        return response_data

    def _make_replay_fn(self, original: Callable, provider: str):
        state = self._state

        @functools.wraps(original)
        def replayed(self_inner, *args, **kwargs):
            ev = state.next_response()
            if ev is None:
                raise RuntimeError(
                    f"FlightBox replay exhausted: no more recorded {provider} responses"
                )
            resp_data = json.loads(ev["response"]) if isinstance(ev["response"], str) else ev["response"]
            if ev.get("error"):
                raise RuntimeError(f"Replayed error: {ev['error']}")
            return self._build_mock_response(provider, resp_data)

        # capture self (ReplayContext) in closure
        ctx = self

        @functools.wraps(original)
        def wrapper(self_inner, *args, **kwargs):
            ev = state.next_response()
            if ev is None:
                raise RuntimeError(
                    f"FlightBox replay exhausted: no more recorded {provider} responses"
                )
            resp_data = json.loads(ev["response"]) if isinstance(ev["response"], str) else ev["response"]
            if ev.get("error"):
                raise RuntimeError(f"Replayed error: {ev['error']}")
            return ctx._build_mock_response(provider, resp_data)

        return wrapper

    def _make_replay_function(self, original: Callable, provider: str):
        state = self._state
        ctx = self

        @functools.wraps(original)
        def wrapper(*args, **kwargs):
            ev = state.next_response()
            if ev is None:
                raise RuntimeError(
                    f"FlightBox replay exhausted: no more recorded {provider} responses"
                )
            resp_data = json.loads(ev["response"]) if isinstance(ev["response"], str) else ev["response"]
            if ev.get("error"):
                raise RuntimeError(f"Replayed error: {ev['error']}")
            return ctx._build_mock_response(provider, resp_data)

        return wrapper

    def _make_async_replay_function(self, original: Callable, provider: str):
        state = self._state
        ctx = self

        @functools.wraps(original)
        async def wrapper(*args, **kwargs):
            ev = state.next_response()
            if ev is None:
                raise RuntimeError(
                    f"FlightBox replay exhausted: no more recorded {provider} responses"
                )
            resp_data = json.loads(ev["response"]) if isinstance(ev["response"], str) else ev["response"]
            if ev.get("error"):
                raise RuntimeError(f"Replayed error: {ev['error']}")
            return ctx._build_mock_response(provider, resp_data)

        return wrapper

    def _patch_openai(self):
        try:
            from openai.resources.chat import completions as mod
            original = mod.Completions.create
            mod.Completions.create = self._make_replay_fn(original, "openai")
            self._patches.append((mod.Completions, "create", original))
        except (ImportError, AttributeError):
            pass

    def _patch_anthropic(self):
        try:
            from anthropic.resources import messages as mod
            original = mod.Messages.create
            mod.Messages.create = self._make_replay_fn(original, "anthropic")
            self._patches.append((mod.Messages, "create", original))
        except (ImportError, AttributeError):
            pass

    def _patch_litellm(self):
        try:
            import litellm

            original = litellm.completion
            litellm.completion = self._make_replay_function(original, "litellm")
            self._patches.append((litellm, "completion", original))
        except (ImportError, AttributeError):
            pass

        try:
            import litellm

            original_async = litellm.acompletion
            litellm.acompletion = self._make_async_replay_function(
                original_async, "litellm"
            )
            self._patches.append((litellm, "acompletion", original_async))
        except (ImportError, AttributeError):
            pass


def replay(run_id: str, store: RecordStore | None = None) -> ReplayContext:
    """Create a replay context for a recorded run.

    Usage:
        with flightbox.replay("abc123") as ctx:
            # your agent code runs here, but LLM calls return recorded responses
            result = my_agent.run("same input")
        print(f"Replayed {ctx.events_replayed} events")
    """
    return ReplayContext(run_id, store)
