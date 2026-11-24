from __future__ import annotations

import json
import threading
import time
from collections import deque
from pathlib import Path

from .config import get_settings


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile. Returns None rather than 0.0 on empty input,
    so an empty window is never mistaken for a fast one."""
    if not values:
        return None
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(round(p / 100.0 * len(s) + 0.5)) - 1))
    return round(s[idx], 2)


class Recorder:
    """Rolling in-process window of request records, plus a JSONL trace file.

    The window is bounded, so /metrics stays O(1) in memory. The JSONL file is
    the durable record: one line per request, replayable offline.
    """

    def __init__(self, maxlen: int = 1000, trace_path: str | None = None) -> None:
        self._lock = threading.Lock()
        self._window: deque[dict] = deque(maxlen=maxlen)
        self._path = Path(trace_path or get_settings().trace_path)
        self._started = time.time()

    def record(self, rec: dict) -> None:
        with self._lock:
            self._window.append(rec)
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, default=str) + "\n")
            except OSError:
                pass  # tracing must never take the request path down

    def snapshot(self) -> dict:
        with self._lock:
            recs = list(self._window)
        if not recs:
            return {"requests": 0, "uptime_s": round(time.time() - self._started, 1)}

        lat = [r["latency_ms"] for r in recs]
        tin = sum(r["tokens_in"] for r in recs)
        tout = sum(r["tokens_out"] for r in recs)
        total_s = sum(lat) / 1000.0
        costs = [r["cost_usd"] for r in recs if r.get("cost_usd") is not None]
        outcomes: dict[str, int] = {}
        for r in recs:
            outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
        node_ms: dict[str, list[float]] = {}
        for r in recs:
            for t in r.get("timings", []):
                node_ms.setdefault(t["node"], []).append(t["ms"])

        answered = outcomes.get("answered", 0)
        return {
            "requests": len(recs),
            "uptime_s": round(time.time() - self._started, 1),
            "latency_ms": {
                "p50": percentile(lat, 50),
                "p95": percentile(lat, 95),
                "p99": percentile(lat, 99),
                "max": round(max(lat), 2),
            },
            "tokens": {
                "in": tin,
                "out": tout,
                "output_tokens_per_sec": round(tout / total_s, 2) if total_s else None,
            },
            "cost_usd": {
                "total": round(sum(costs), 6) if costs else None,
                "mean_per_request": round(sum(costs) / len(costs), 8) if costs else None,
                "priced_requests": len(costs),
                "note": None if costs else "unconfigured — see config/pricing.yaml",
            },
            "outcomes": outcomes,
            "answer_rate": round(answered / len(recs), 4),
            "refusal_rate": round(1 - answered / len(recs), 4),
            "node_latency_ms_p95": {k: percentile(v, 95) for k, v in sorted(node_ms.items())},
        }
