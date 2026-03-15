"""Record LLM calls by monkey-patching the OpenAI / Anthropic SDKs."""

from __future__ import annotations

import functools
import time
from contextlib import contextmanager
from typing import Any, Callable

from flightbox.store import RecordStore


class FlightRecorder:
    """Intercepts LLM SDK calls and writes them to a RecordStore."""

    def __init__(
        self,
        store: RecordStore | None = None,
        name: str | None = None,
        metadata: dict | None = None,
    ):
        self.store = store or RecordStore()
        self.name = name
        self.metadata = metadata
        self._run_id: str | None = None
        self._seq = 0
        self._patches: list[tuple[Any, str, Any]] = []  # (obj, attr, original)

    @property
    def run_id(self) -> str | None:
        return self._run_id

    # -- lifecycle --

    def start(self) -> str:
        self._run_id = self.store.create_run(name=self.name, metadata=self.metadata)
        self._seq = 0
        self._patch_openai()
        self._patch_anthropic()
        return self._run_id

    def stop(self):
        self._unpatch_all()
        if self._run_id:
            self.store.finish_run(self._run_id)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    # -- patching --

    def _patch_openai(self):
        try:
            from openai.resources.chat import completions as mod

            original = mod.Completions.create
            recorder = self

            @functools.wraps(original)
            def patched_create(self_inner, *args, **kwargs):
                return recorder._wrap_call(
                    original, self_inner, "openai", args, kwargs
                )

            mod.Completions.create = patched_create
            self._patches.append((mod.Completions, "create", original))
        except (ImportError, AttributeError):
            pass

        # async variant
        try:
            from openai.resources.chat import completions as mod

            original_async = mod.AsyncCompletions.create
            recorder = self

            @functools.wraps(original_async)
            async def patched_async_create(self_inner, *args, **kwargs):
                return await recorder._wrap_async_call(
                    original_async, self_inner, "openai", args, kwargs
                )

            mod.AsyncCompletions.create = patched_async_create
            self._patches.append((mod.AsyncCompletions, "create", original_async))
        except (ImportError, AttributeError):
            pass

    def _patch_anthropic(self):
        try:
            from anthropic.resources import messages as mod

            original = mod.Messages.create
            recorder = self

            @functools.wraps(original)
            def patched_create(self_inner, *args, **kwargs):
                return recorder._wrap_call(
                    original, self_inner, "anthropic", args, kwargs
                )

            mod.Messages.create = patched_create
            self._patches.append((mod.Messages, "create", original))
        except (ImportError, AttributeError):
            pass

    def _unpatch_all(self):
        for obj, attr, original in reversed(self._patches):
            setattr(obj, attr, original)
        self._patches.clear()

    # -- call interception --

    def _extract_info(self, provider: str, kwargs: dict) -> tuple[str | None, dict, dict | None]:
        """Pull model name, serializable request, and token usage from kwargs/response."""
        model = kwargs.get("model")
        # build a serializable copy of the request
        req = {}
        for key in ("model", "messages", "tools", "temperature", "max_tokens",
                     "top_p", "stop", "stream", "system"):
            if key in kwargs:
                req[key] = kwargs[key]
        return model, req, None

    def _extract_usage(self, provider: str, response: Any) -> dict | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        return {
            "prompt_tokens": getattr(usage, "prompt_tokens", None)
            or getattr(usage, "input_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None)
            or getattr(usage, "output_tokens", None),
        }

    def _serialize_response(self, response: Any) -> Any:
        if hasattr(response, "model_dump"):
            return response.model_dump()
        if hasattr(response, "to_dict"):
            return response.to_dict()
        return str(response)

    def _wrap_call(
        self, original: Callable, instance: Any, provider: str,
        args: tuple, kwargs: dict,
    ) -> Any:
        model, req, _ = self._extract_info(provider, kwargs)
        self._seq += 1
        seq = self._seq
        t0 = time.perf_counter()
        error = None
        response = None
        try:
            response = original(instance, *args, **kwargs)
            return response
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            raise
        finally:
            latency = (time.perf_counter() - t0) * 1000
            usage = self._extract_usage(provider, response) if response else None
            resp_data = self._serialize_response(response) if response else None
            if self._run_id:
                self.store.add_event(
                    self._run_id, seq, "llm_call",
                    provider=provider, model=model,
                    request=req, response=resp_data,
                    latency_ms=latency, token_usage=usage, error=error,
                )

    async def _wrap_async_call(
        self, original: Callable, instance: Any, provider: str,
        args: tuple, kwargs: dict,
    ) -> Any:
        model, req, _ = self._extract_info(provider, kwargs)
        self._seq += 1
        seq = self._seq
        t0 = time.perf_counter()
        error = None
        response = None
        try:
            response = await original(instance, *args, **kwargs)
            return response
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            raise
        finally:
            latency = (time.perf_counter() - t0) * 1000
            usage = self._extract_usage(provider, response) if response else None
            resp_data = self._serialize_response(response) if response else None
            if self._run_id:
                self.store.add_event(
                    self._run_id, seq, "llm_call",
                    provider=provider, model=model,
                    request=req, response=resp_data,
                    latency_ms=latency, token_usage=usage, error=error,
                )


@contextmanager
def record(name: str | None = None, store: RecordStore | None = None, **meta):
    """Context manager to record all LLM calls within a block.

    Usage:
        with flightbox.record("my-test") as rec:
            client.chat.completions.create(...)
        print(rec.run_id)
    """
    recorder = FlightRecorder(store=store, name=name, metadata=meta)
    recorder.start()
    try:
        yield recorder
    finally:
        recorder.stop()
