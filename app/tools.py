"""The agent's toolbox.

A tool is a name, a description the model reads, a JSON argument schema, and a
Python callable. The agent chooses which to call; it is not hard-wired to any
of them. That choice is what makes this an agent rather than a pipeline, and
it is what `tool_selection_accuracy` in the eval harness measures.

Every tool returns a dict with an `ok` flag. A tool that raises is caught and
returned as `{"ok": False, "error": ...}` so one bad call degrades the step
instead of killing the request — the agent sees the failure and can choose
differently on the next turn.
"""

from __future__ import annotations

import ast
import datetime as _dt
import operator
import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    args: dict[str, str]  # arg name -> human description
    fn: Callable[..., dict]

    def spec(self) -> str:
        arglist = ", ".join(f"{k} ({v})" for k, v in self.args.items()) or "no arguments"
        return f"- {self.name}({arglist}): {self.description}"


# ---------------------------------------------------------------- calculator

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval(expression: str) -> float:
    """Arithmetic only, parsed from an AST.

    Deliberately not eval(). The expression string comes from a language model,
    which means it is untrusted input; eval() on model output is a remote code
    execution hole with extra steps.
    """
    tree = ast.parse(expression, mode="eval")

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ValueError(f"only numbers are allowed, got {node.value!r}")
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.operand))
        raise ValueError(f"unsupported expression element: {type(node).__name__}")

    return walk(tree)


# -------------------------------------------------------------- tool factory


def build_toolbox(store) -> dict[str, Tool]:
    def search_documents(query: str) -> dict:
        hits = store.search(query)
        return {
            "ok": True,
            "hits": [
                {
                    "chunk_id": h.chunk.chunk_id,
                    "source": h.chunk.source,
                    "page": h.chunk.page,
                    "score": h.fused_score,
                    "text": h.chunk.text[:900],
                }
                for h in hits
            ],
            "count": len(hits),
        }

    def lookup_number(query: str) -> dict:
        """Retrieval biased toward passages that actually contain figures.

        Dense embeddings blur exact numbers, and an eligibility answer usually
        turns on one. This re-ranks the hybrid results so chunks containing
        digits, percentages or currency come first.
        """
        hits = store.search(query)
        numeric = re.compile(r"\d")
        ranked = sorted(hits, key=lambda h: (not bool(numeric.search(h.chunk.text)), -h.fused_score))
        return {
            "ok": True,
            "hits": [
                {
                    "chunk_id": h.chunk.chunk_id,
                    "source": h.chunk.source,
                    "page": h.chunk.page,
                    "has_figures": bool(numeric.search(h.chunk.text)),
                    "text": h.chunk.text[:900],
                }
                for h in ranked[:5]
            ],
        }

    def calculate(expression: str) -> dict:
        try:
            return {"ok": True, "expression": expression, "result": safe_eval(expression)}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def current_date() -> dict:
        today = _dt.date.today()
        return {"ok": True, "today": today.isoformat(), "year": today.year}

    def finish(reason: str = "") -> dict:
        return {"ok": True, "finished": True, "reason": reason}

    tools = [
        Tool(
            "search_documents",
            "Search the ingested documents for passages relevant to a query. Use this first for any factual question.",
            {"query": "what to search for, in the wording the documents would use"},
            search_documents,
        ),
        Tool(
            "lookup_number",
            "Search specifically for passages containing figures — amounts, limits, percentages, thresholds. Use when the answer turns on a number.",
            {"query": "the figure you are looking for, e.g. 'income limit' or 'benefit amount'"},
            lookup_number,
        ),
        Tool(
            "calculate",
            "Evaluate an arithmetic expression. Use for threshold comparisons and totals instead of doing the arithmetic yourself.",
            {"expression": "arithmetic only, e.g. '1.5 <= 2' is NOT valid; use '2 - 1.5'"},
            calculate,
        ),
        Tool(
            "current_date",
            "Get today's date. Use when the question depends on whether a window or deadline is still open.",
            {},
            current_date,
        ),
        Tool(
            "finish",
            "Stop gathering evidence. Call this when you have enough to answer, or when the documents clearly cannot answer the question.",
            {"reason": "one short sentence on why you are stopping"},
            finish,
        ),
    ]
    return {t.name: t for t in tools}


def toolbox_spec(toolbox: dict[str, Tool]) -> str:
    return "\n".join(t.spec() for t in toolbox.values())


def run_tool(toolbox: dict[str, Tool], name: str, args: dict[str, Any]) -> dict:
    tool = toolbox.get(name)
    if tool is None:
        return {"ok": False, "error": f"no such tool: {name!r}. Available: {list(toolbox)}"}
    allowed = set(tool.args)
    clean = {k: v for k, v in (args or {}).items() if k in allowed}
    missing = allowed - set(clean)
    if missing:
        return {"ok": False, "error": f"missing arguments for {name}: {sorted(missing)}"}
    try:
        return tool.fn(**clean)
    except Exception as exc:  # a failing tool degrades the step, not the request
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
