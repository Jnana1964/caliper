"""Evaluation harness.

    python eval/run_eval.py                      # with the verify node
    python eval/run_eval.py --no-verify          # ablation, verify disabled
    python eval/run_eval.py --compare            # run both, print the delta

What it measures
  answer accuracy    on answerable questions: did the answer contain the facts
                     it should, and cite the right document
  hallucination rate on unanswerable questions: how often the system answered
                     when it had no business answering. This is the number the
                     verify node exists to reduce, and the one worth publishing
                     whichever way it comes out
  routing accuracy   on out_of_scope questions: refused at the router
  cost and latency   p50/p95, tokens, and USD when pricing.yaml is verified

Nothing here is graded by a model marking its own homework: the checks are
substring and citation assertions against a human-written answer key.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.graph.build import build_graph  # noqa: E402
from app.llm import Meter, get_llm  # noqa: E402
from app.observability import percentile  # noqa: E402
from app.store import HybridStore, InMemoryStore  # noqa: E402


def load_questions(path: Path) -> list[dict]:
    if not path.exists():
        alt = path.with_name("questions.example.yaml")
        if not alt.exists():
            raise SystemExit(f"no question set at {path}")
        print(f"note: {path.name} not found, using {alt.name} (fictional fixture questions)\n")
        path = alt
    return yaml.safe_load(path.read_text())


def grade_one(q: dict, out: dict) -> dict:
    kind = q["kind"]
    outcome = out.get("outcome", "")
    answer = (out.get("answer") or "").lower()
    sources = {c.source for c in out.get("citations", [])}
    refused = outcome.startswith("refused")

    row = {"id": q["id"], "kind": kind, "outcome": outcome, "pass": False, "why": ""}

    if kind == "out_of_scope":
        row["pass"] = outcome == "refused_out_of_scope"
        row["why"] = "" if row["pass"] else f"expected router refusal, got {outcome}"
    elif kind == "unanswerable":
        row["pass"] = refused
        row["why"] = "" if row["pass"] else "ANSWERED a question the corpus cannot support"
    else:
        missing = [s for s in (q.get("must_contain") or []) if s.lower() not in answer]
        banned = [s for s in (q.get("must_not_contain") or []) if s.lower() in answer]
        want_src = q.get("expect_source")
        src_ok = (want_src in sources) if want_src else True
        row["pass"] = (not refused) and not missing and not banned and src_ok
        reasons = []
        if refused:
            reasons.append(f"refused ({outcome})")
        if missing:
            reasons.append(f"missing {missing}")
        if banned:
            reasons.append(f"contains banned {banned}")
        if not src_ok:
            reasons.append(f"cited {sorted(sources) or 'nothing'}, expected {want_src}")
        row["why"] = "; ".join(reasons)
        row["answer"] = (out.get("answer") or "")[:600]
        row["citations"] = sorted(sources)
    return row


def run(questions: list[dict], enable_verify: bool) -> dict:
    s = get_settings()
    llm = get_llm()
    if s.is_offline:
        sys.path.insert(0, str(ROOT))
        from tests.fixtures import fixture_chunks

        store = InMemoryStore(llm, fixture_chunks())
    else:
        store = HybridStore(llm)
        store.load_lexical_index()

    graph = build_graph(llm, store, enable_verify=enable_verify)
    rows, lats, costs = [], [], []
    tin = tout = 0

    for q in questions:
        meter = Meter()
        t0 = time.perf_counter()
        out = graph.invoke(
            {"question": q["question"], "rewrites": 0, "timings": [], "meter": meter}
        )
        lat = (time.perf_counter() - t0) * 1000
        lats.append(lat)
        tin += meter.tokens_in
        tout += meter.tokens_out
        c, _ = meter.cost_usd()
        if c is not None:
            costs.append(c)
        row = grade_one(q, out)
        row["latency_ms"] = round(lat, 1)
        rows.append(row)

    by_kind: dict[str, list[dict]] = {}
    for r in rows:
        by_kind.setdefault(r["kind"], []).append(r)

    def rate(kind: str) -> float | None:
        group = by_kind.get(kind)
        if not group:
            return None
        return round(sum(r["pass"] for r in group) / len(group), 4)

    unans = by_kind.get("unanswerable", [])
    hallucinated = [r for r in unans if not r["pass"]]

    return {
        "verify_enabled": enable_verify,
        "n": len(rows),
        "rows": rows,
        "answer_accuracy": rate("answerable"),
        "refusal_accuracy": rate("unanswerable"),
        "routing_accuracy": rate("out_of_scope"),
        "hallucination_rate": round(len(hallucinated) / len(unans), 4) if unans else None,
        "hallucinated_ids": [r["id"] for r in hallucinated],
        "latency_ms": {
            "p50": percentile(lats, 50),
            "p95": percentile(lats, 95),
            "mean": round(statistics.mean(lats), 1) if lats else None,
        },
        "tokens": {"in": tin, "out": tout},
        "cost_usd": round(sum(costs), 6) if costs else None,
    }


def print_report(r: dict) -> None:
    tag = "verify ON " if r["verify_enabled"] else "verify OFF"
    print(f"\n=== {tag} | {r['n']} questions ===")
    for row in r["rows"]:
        mark = "PASS" if row["pass"] else "FAIL"
        print(f"  [{mark}] {row['id']:<22} {row['kind']:<13} {row['outcome']:<22} {row['why']}")
    print(f"\n  answer accuracy    : {r['answer_accuracy']}")
    print(f"  refusal accuracy   : {r['refusal_accuracy']}")
    print(f"  routing accuracy   : {r['routing_accuracy']}")
    print(f"  hallucination rate : {r['hallucination_rate']}  {r['hallucinated_ids'] or ''}")
    print(f"  latency p50/p95 ms : {r['latency_ms']['p50']} / {r['latency_ms']['p95']}")
    print(f"  tokens in/out      : {r['tokens']['in']} / {r['tokens']['out']}")
    print(f"  cost usd           : {r['cost_usd'] if r['cost_usd'] is not None else 'unconfigured'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", type=Path, default=ROOT / "eval" / "questions.yaml")
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--compare", action="store_true", help="run with and without the verify node")
    ap.add_argument("--json-out", type=Path, default=ROOT / "eval" / "results.json")
    args = ap.parse_args()

    questions = load_questions(args.questions)

    if get_settings().is_offline:
        print(
            "\n" + "!" * 78 + "\n"
            "OFFLINE=1 — these numbers measure NOTHING about answer quality.\n"
            "The offline stub answers every question with fixed text, grades every\n"
            "chunk relevant and always votes 'grounded', so every check fails by\n"
            "construction. This mode exists to prove the harness itself runs end to\n"
            "end in CI without an API key. Unset OFFLINE and ingest real documents\n"
            "before quoting any figure from this report.\n" + "!" * 78
        )

    if args.compare:
        off = run(questions, enable_verify=False)
        on = run(questions, enable_verify=True)
        print_report(off)
        print_report(on)
        a, b = off["hallucination_rate"], on["hallucination_rate"]
        print("\n=== ablation ===")
        if a is None or b is None:
            print("  no unanswerable questions in the set, so the verify node cannot be scored")
        else:
            delta = round(a - b, 4)
            caliper = (
                f"verify node removed {delta:.0%} of ungrounded answers"
                if delta > 0
                else "verify node caught nothing on this set"
                if delta == 0
                else f"verify node made it WORSE by {abs(delta):.0%}"
            )
            print(f"  hallucination rate: {a} -> {b}   {caliper}")
            print(f"  extra tokens for verify: {on['tokens']['in'] - off['tokens']['in']} in")
        args.json_out.write_text(json.dumps({"verify_off": off, "verify_on": on}, indent=2))
    else:
        r = run(questions, enable_verify=not args.no_verify)
        print_report(r)
        args.json_out.write_text(json.dumps(r, indent=2))

    print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
