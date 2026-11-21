import hashlib
import json
import time
from dataclasses import dataclass

import litellm

from .config import settings

litellm.suppress_debug_info = True
litellm.cache = litellm.Cache(type="local")

RETRYABLE_STATUSES = {429, 500, 502, 503}


class SimulatedFailure(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"simulated failure {status_code}")


class AllProvidersUnavailable(Exception):
    pass


@dataclass
class ChatResult:
    reply: str
    resolution_source: str
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: str | None
    fallback_attempts: int


def parse_simulate_header(header_value: str | None) -> dict[str, int]:
    """Parses 'key_1=429,key_2=500' or '*=429' into {key_id: status}."""
    if not header_value:
        return {}
    result = {}
    for pair in header_value.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        key_id, status = pair.split("=", 1)
        key_id = key_id.strip()
        try:
            result[key_id] = int(status.strip())
        except ValueError:
            continue
    return result


def _cache_key(model: str, messages: list[dict]) -> str:
    payload = json.dumps({"model": model, "messages": messages}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_status_code(exc: Exception) -> int:
    code = getattr(exc, "status_code", None)
    if code:
        try:
            return int(code)
        except (TypeError, ValueError):
            pass
    message = str(exc).lower()
    if "429" in message or "rate limit" in message or "quota" in message:
        return 429
    if "503" in message:
        return 503
    if "502" in message:
        return 502
    if "500" in message:
        return 500
    return 500


class KeyPool:
    def __init__(self):
        self.keys = settings.llm_api_keys
        self.key_ids = settings.key_ids
        self.model = settings.llm_model
        # application-level cache, source of truth for resolution_source / tokens
        self._cache: dict[str, dict] = {}

    @property
    def configured_count(self) -> int:
        return len(self.keys)

    def chat(
        self,
        messages: list[dict],
        simulate: dict[str, int] | None = None,
    ) -> ChatResult:
        simulate = simulate or {}
        start = time.perf_counter()
        key = _cache_key(self.model, messages)

        cached = self._cache.get(key)
        if cached is not None:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ChatResult(
                reply=cached["reply"],
                resolution_source="LLM_CACHE",
                model=cached["model"],
                latency_ms=latency_ms,
                input_tokens=cached["input_tokens"],
                output_tokens=cached["output_tokens"],
                key_id=None,
                fallback_attempts=0,
            )

        if not self.keys:
            raise AllProvidersUnavailable()

        fallback_attempts = 0
        last_error = None

        for idx, api_key in enumerate(self.keys):
            key_id = self.key_ids[idx]
            forced_status = simulate.get(key_id) or simulate.get("*")

            try:
                if forced_status is not None:
                    raise SimulatedFailure(forced_status)

                response = litellm.completion(
                    model=self.model,
                    api_key=api_key,
                    messages=messages,
                    caching=False,  # we manage our own cache layer
                )
                latency_ms = int((time.perf_counter() - start) * 1000)
                usage = getattr(response, "usage", None)
                input_tokens = getattr(usage, "prompt_tokens", 0) or 0
                output_tokens = getattr(usage, "completion_tokens", 0) or 0
                reply = response.choices[0].message.content or ""

                self._cache[key] = {
                    "reply": reply,
                    "model": self.model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                }

                return ChatResult(
                    reply=reply,
                    resolution_source="LIVE_INFERENCE",
                    model=self.model,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    key_id=key_id,
                    fallback_attempts=fallback_attempts,
                )

            except SimulatedFailure as exc:
                last_error = exc
                if exc.status_code in RETRYABLE_STATUSES:
                    fallback_attempts += 1
                    continue
                raise AllProvidersUnavailable() from exc

            except Exception as exc:  # noqa: BLE001 - broad: provider SDK raises many types
                last_error = exc
                status = _extract_status_code(exc)
                if status in RETRYABLE_STATUSES:
                    fallback_attempts += 1
                    continue
                raise AllProvidersUnavailable() from exc

        raise AllProvidersUnavailable() from last_error


key_pool = KeyPool()
