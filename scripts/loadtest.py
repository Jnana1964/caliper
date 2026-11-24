"""Concurrency load test against a running service.

    python scripts/loadtest.py --url http://localhost:8000 --concurrency 8 --requests 80

Reports p50/p95/p99 latency, throughput, error count, and the outcome mix.
Deliberately prints the error count and the slowest request alongside the
favourable numbers: a load test that only reports the mean is marketing.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx

QUESTIONS = [
    "What is the annual benefit amount under the scheme?",
    "Who is eligible to apply?",
    "What documents are required?",
    "When does the application window close?",
    "Is there an income limit?",
]


async def one(client: httpx.AsyncClient, url: str, q: str) -> tuple[float, int, str]:
    t0 = time.perf_counter()
    try:
        r = await client.post(f"{url}/ask", json={"question": q}, timeout=120.0)
        ms = (time.perf_counter() - t0) * 1000
        outcome = r.json().get("outcome", "?") if r.status_code == 200 else f"http_{r.status_code}"
        return ms, r.status_code, outcome
    except Exception as exc:
        return (time.perf_counter() - t0) * 1000, 0, type(exc).__name__


async def main_async(url: str, concurrency: int, total: int) -> None:
    sem = asyncio.Semaphore(concurrency)
    results: list[tuple[float, int, str]] = []

    async with httpx.AsyncClient() as client:
        async def guarded(i: int):
            async with sem:
                results.append(await one(client, url, QUESTIONS[i % len(QUESTIONS)]))

        t0 = time.perf_counter()
        await asyncio.gather(*(guarded(i) for i in range(total)))
        wall = time.perf_counter() - t0

    lats = sorted(r[0] for r in results)
    errors = [r for r in results if r[1] != 200]
    outcomes: dict[str, int] = {}
    for _, _, o in results:
        outcomes[o] = outcomes.get(o, 0) + 1

    def pct(p: float) -> float:
        return round(lats[max(0, min(len(lats) - 1, int(p / 100 * len(lats)) - 1))], 1)

    print(f"requests        : {total} at concurrency {concurrency}")
    print(f"wall time       : {wall:.2f}s")
    print(f"throughput      : {total / wall:.2f} req/s")
    print(f"latency p50     : {pct(50)} ms")
    print(f"latency p95     : {pct(95)} ms")
    print(f"latency p99     : {pct(99)} ms")
    print(f"latency max     : {round(lats[-1], 1)} ms")
    print(f"mean            : {round(statistics.mean(lats), 1)} ms")
    print(f"errors          : {len(errors)}" + (f"  {errors[:3]}" if errors else ""))
    print(f"outcomes        : {outcomes}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--requests", type=int, default=40)
    a = ap.parse_args()
    asyncio.run(main_async(a.url, a.concurrency, a.requests))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
