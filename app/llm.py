from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field

from .config import get_pricing, get_settings


@dataclass
class LLMResult:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    model: str = ""

    def json(self) -> dict:
        """Parse the model's reply as JSON, tolerating ```json fences."""
        raw = self.text.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
        if fence:
            raw = fence.group(1).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end > start:
                try:
                    return json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    pass
        return {}


@dataclass
class Meter:
    """Accumulates token usage across every LLM call in one request."""

    tokens_in: int = 0
    tokens_out: int = 0
    calls: int = 0
    model: str = ""
    _by_model: dict[str, list[int]] = field(default_factory=dict)

    def add(self, r: LLMResult) -> LLMResult:
        self.tokens_in += r.tokens_in
        self.tokens_out += r.tokens_out
        self.calls += 1
        self.model = r.model or self.model
        slot = self._by_model.setdefault(r.model, [0, 0])
        slot[0] += r.tokens_in
        slot[1] += r.tokens_out
        return r

    def cost_usd(self) -> tuple[float | None, str | None]:
        pricing = get_pricing()
        if not pricing.verified:
            return None, (
                "config/pricing.yaml has verified: false — fill in the rates from "
                f"{pricing.source_url} and set verified: true to get real cost figures"
            )
        total = 0.0
        for model, (tin, tout) in self._by_model.items():
            c = pricing.cost_usd(model, tin, tout)
            if c is None:
                return None, f"no verified pricing for model {model!r} in config/pricing.yaml"
            total += c
        return round(total, 8), None


class OfflineLLM:
    """Deterministic stub. No network, no key, no cost.

    Exists so the graph, the API and the whole test suite can run in CI without
    credentials, and so an eval run can be reproduced byte for byte.
    """

    model = "offline-stub"

    def generate(self, prompt: str, system: str | None = None, **_: object) -> LLMResult:
        """Branch on the node markers the prompts carry (#ROUTE, #GRADE, ...).

        Two words in the question steer the stub so tests can drive each branch:
        'offtopic' makes the router refuse, 'ungrounded' makes verify refuse.
        """
        t0 = time.perf_counter()
        question = ""
        m = re.search(r"QUESTION:\s*(.+)", prompt)
        if m:
            question = m.group(1).strip().lower()

        if "#PLAN" in prompt:
            # first turn searches, every later turn stops — deterministic, so the
            # agent-loop tests assert on an exact tool sequence
            first = "(nothing gathered yet)" in prompt
            out = (
                json.dumps(
                    {"thought": "stub: search first", "tool": "search_documents",
                     "args": {"query": question or "stub"}}
                )
                if first
                else json.dumps({"thought": "stub: enough", "tool": "finish", "args": {"reason": "stub"}})
            )
        elif "#ROUTE" in prompt:
            out = json.dumps({"in_scope": "offtopic" not in question, "reason": "stub"})
        elif "#GRADE" in prompt:
            ids = re.findall(r"\[\[([0-9a-fA-F\-]{8,})\]\]", prompt)
            keep = [] if "noevidence" in question else ids
            out = json.dumps({"relevant_ids": keep})
        elif "#REWRITE" in prompt:
            out = json.dumps({"query": f"{question} scheme eligibility criteria"})
        elif "#VERIFY" in prompt:
            ok = "ungrounded" not in question
            out = json.dumps(
                {
                    "caliper": "grounded" if ok else "ungrounded",
                    "grounded": ok,
                    "unsupported": [] if ok else ["stub unsupported claim"],
                }
            )
        else:
            digest = hashlib.sha256(prompt.encode()).hexdigest()[:8]
            out = f"Stub answer [S1]. (deterministic digest {digest})"
        ms = (time.perf_counter() - t0) * 1000
        return LLMResult(out, len(prompt) // 4, len(out) // 4, ms, self.model)

    def embed(self, texts: list[str], dim: int = 768, **_: object) -> list[list[float]]:
        """Hash-based pseudo-embedding: stable, deterministic, no network.

        Not semantically meaningful. Good enough to exercise the plumbing and to
        make retrieval tests deterministic; never used when OFFLINE=0.
        """
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            vec = [((h[i % len(h)] / 255.0) - 0.5) for i in range(dim)]
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            out.append([v / norm for v in vec])
        return out


class GeminiLLM:
    def __init__(self) -> None:
        from google import genai  # imported lazily so offline mode needs no SDK key

        s = get_settings()
        if not s.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set. Set it in .env, or run with OFFLINE=1.")
        self._client = genai.Client(api_key=s.gemini_api_key)
        self._s = s
        self.model = s.gen_model

    # Transient server side conditions. 429 is the free tier rate limit, 503 is
    # the model being overloaded, 500 is an internal fault. None of them mean
    # the request was wrong, so all of them are worth retrying.
    _RETRYABLE = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "500", "INTERNAL")

    def _with_retry(self, fn, label: str, attempts: int = 6):
        """Call fn, backing off on transient API failures.

        When the API states how long to wait, that figure is honoured rather
        than guessed at. A non transient error is re-raised immediately, so a
        bad request still fails fast instead of being retried six times.
        """
        wait = 4.0
        for attempt in range(1, attempts + 1):
            try:
                return fn()
            except Exception as exc:
                msg = str(exc)
                if attempt == attempts or not any(t in msg for t in self._RETRYABLE):
                    raise
                m = re.search(r"retry in ([0-9.]+)s", msg)
                pause = float(m.group(1)) + 3 if m else wait
                print(
                    f"  {label}: transient API failure, sleeping {pause:.0f}s "
                    f"(attempt {attempt} of {attempts})",
                    flush=True,
                )
                time.sleep(pause)
                wait = min(wait * 2, 90)

    def generate(self, prompt: str, system: str | None = None, json_out: bool = False) -> LLMResult:
        from google.genai import types

        cfg = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.0,
            response_mime_type="application/json" if json_out else None,
        )
        t0 = time.perf_counter()
        resp = self._with_retry(
            lambda: self._client.models.generate_content(
                model=self._s.gen_model, contents=prompt, config=cfg
            ),
            "generate",
        )
        ms = (time.perf_counter() - t0) * 1000
        u = getattr(resp, "usage_metadata", None)
        return LLMResult(
            text=resp.text or "",
            tokens_in=getattr(u, "prompt_token_count", 0) or 0,
            tokens_out=getattr(u, "candidates_token_count", 0) or 0,
            latency_ms=ms,
            model=self._s.gen_model,
        )

    def embed(self, texts: list[str], dim: int | None = None, task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
        """Embed a batch, retrying on transient API failures.

        Google counts every piece of text as one request against the per minute
        embedding quota, so a batch of 50 spends 50 of the allowance. When the
        quota is exhausted the API replies 429 and states how long to wait; that
        figure is parsed and honoured rather than guessed at.
        """
        from google.genai import types

        cfg = types.EmbedContentConfig(
            task_type=task, output_dimensionality=dim or self._s.embed_dim
        )
        resp = self._with_retry(
            lambda: self._client.models.embed_content(
                model=self._s.embed_model, contents=texts, config=cfg
            ),
            "embed",
            attempts=8,
        )
        return [list(e.values) for e in resp.embeddings]


def get_llm():
    return OfflineLLM() if get_settings().is_offline else GeminiLLM()