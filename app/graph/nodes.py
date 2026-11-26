"""Graph nodes.

Each node takes the state, does one job, and returns only the keys it changed.
Every node that calls the model records its own latency and token usage, so the
per-request trace shows where the time and the money actually went.

The `#ROUTE`, `#GRADE`, `#REWRITE` and `#VERIFY` markers in the prompts are read
by the offline stub in app/llm.py to pick a canned reply. They are inert for a
real model, which reads the instructions below them.
"""

from __future__ import annotations

import time

from ..models import Citation, NodeTiming, Retrieved
from .state import GraphState

SYSTEM = (
    "You answer questions about Indian government welfare schemes using only the "
    "excerpts provided. You never rely on prior knowledge about a scheme, because "
    "eligibility rules and amounts change and a confident wrong answer can cost "
    "someone a benefit they are entitled to."
)


def _cited_markers(text: str) -> set[int]:
    """Marker numbers actually cited in an answer.

    The model writes citations in several shapes: [S1], [S1, S2] and [S1][S2].
    Testing for the literal string "[S1]" matches only the first, so a grouped
    citation produced an answer that displayed markers with no sources behind
    it: the one failure this system must not have. Numbers are read only from
    inside bracketed groups, so a stray "S1" in prose is not mistaken for a
    citation.
    """
    import re

    out: set[int] = set()
    for group in re.findall(r"\[([^\]]+)\]", text):
        out.update(int(n) for n in re.findall(r"S(\d+)", group))
    return out


def _timed(node: str):
    def deco(fn):
        def wrapper(state: GraphState, *a, **kw):
            t0 = time.perf_counter()
            before = state["meter"].tokens_in, state["meter"].tokens_out
            out = fn(state, *a, **kw)
            after = state["meter"].tokens_in, state["meter"].tokens_out
            timing = NodeTiming(
                node=node,
                ms=round((time.perf_counter() - t0) * 1000, 2),
                tokens_in=after[0] - before[0],
                tokens_out=after[1] - before[1],
            )
            out["timings"] = state.get("timings", []) + [timing]
            return out

        return wrapper

    return deco


def _format_excerpts(items: list[Retrieved]) -> str:
    return "\n\n".join(
        f"[S{i}] (source: {r.chunk.source}, page: {r.chunk.page}) [[{r.chunk.chunk_id}]]\n{r.chunk.text}"
        for i, r in enumerate(items, start=1)
    )


def make_nodes(llm, store):
    @_timed("route")
    def route(state: GraphState) -> dict:
        prompt = (
            "#ROUTE\nClassify whether the question can be answered from a corpus of "
            "Indian government welfare scheme documents (eligibility, benefits, "
            "application process, documents required).\n"
            'Reply as JSON: {"in_scope": true|false, "reason": "<short>"}\n\n'
            f"QUESTION: {state['question']}"
        )
        res = state["meter"].add(llm.generate(prompt, system=SYSTEM, json_out=True))
        data = res.json()
        if data.get("in_scope") is False:
            return {
                "outcome": "refused_out_of_scope",
                "answer": (
                    "That question is outside this corpus. This service only answers "
                    "from the Indian government scheme documents it has ingested."
                ),
            }
        return {"query": state["question"], "rewrites": state.get("rewrites", 0)}

    @_timed("retrieve")
    def retrieve(state: GraphState) -> dict:
        hits = store.search(state.get("query") or state["question"])
        return {"retrieved": hits}

    @_timed("grade")
    def grade(state: GraphState) -> dict:
        """Self-reflection step one: is what we retrieved actually usable?

        Without this, a RAG system cheerfully answers from loosely related text.
        Grading first is what makes the 'no evidence' refusal possible at all.
        """
        items = state.get("retrieved", [])
        if not items:
            return {"relevant": []}
        prompt = (
            "#GRADE\nFor each excerpt, decide whether it contains information that "
            "helps answer the question. Be strict: topical overlap is not relevance.\n"
            'Reply as JSON: {"relevant_ids": ["<id>", ...]} using the ids in [[double brackets]].\n\n'
            f"QUESTION: {state['question']}\n\n{_format_excerpts(items)}"
        )
        res = state["meter"].add(llm.generate(prompt, system=SYSTEM, json_out=True))
        keep = set(res.json().get("relevant_ids") or [])
        relevant = []
        for r in items:
            r.relevant = r.chunk.chunk_id in keep
            if r.relevant:
                relevant.append(r)
        return {"retrieved": items, "relevant": relevant}

    @_timed("rewrite")
    def rewrite(state: GraphState) -> dict:
        prompt = (
            "#REWRITE\nThe search returned nothing relevant. Rewrite the query to match "
            "the wording of official scheme documents: expand abbreviations, add the "
            "likely scheme name, use formal terms.\n"
            'Reply as JSON: {"query": "<rewritten>"}\n\n'
            f"ORIGINAL QUESTION: {state['question']}\n"
            f"LAST QUERY: {state.get('query')}"
        )
        res = state["meter"].add(llm.generate(prompt, system=SYSTEM, json_out=True))
        new_q = (res.json().get("query") or "").strip() or state["question"]
        return {"query": new_q, "rewrites": state.get("rewrites", 0) + 1}

    @_timed("generate")
    def generate(state: GraphState) -> dict:
        items = state["relevant"]
        prompt = (
            "Answer the question using only the excerpts. Cite every factual claim "
            "inline with its marker, like [S1] or [S2]. If the excerpts do not settle "
            "part of the question, say so plainly instead of filling the gap.\n"
            "Do not add caveats about consulting officials; just answer and cite.\n\n"
            f"QUESTION: {state['question']}\n\n{_format_excerpts(items)}"
        )
        res = state["meter"].add(llm.generate(prompt, system=SYSTEM))
        text = res.text.strip()
        cited = _cited_markers(text)
        cites = [
            Citation(
                marker=f"S{i}",
                source=r.chunk.source,
                page=r.chunk.page,
                chunk_id=r.chunk.chunk_id,
            )
            for i, r in enumerate(items, start=1)
            if i in cited
        ]
        return {"answer": text, "citations": cites}

    @_timed("verify")
    def verify(state: GraphState) -> dict:
        """Self-reflection step two: is the drafted answer actually supported?

        The measurable point of the whole project. Run the eval with this node
        disabled and with it enabled, and the difference is the ungrounded-answer
        rate it catches. That number is in the README, whatever it turns out to be.
        """
        prompt = (
            "#VERIFY\nCheck the draft answer against the excerpts. A claim is supported "
            "only if an excerpt states it. Inference beyond the text is not support.\n"
            'Reply as JSON: {"caliper": "grounded"|"ungrounded", "grounded": true|false, '
            '"unsupported": ["<claim>", ...]}\n\n'
            f"QUESTION: {state['question']}\n\nDRAFT ANSWER:\n{state['answer']}\n\n"
            f"{_format_excerpts(state['relevant'])}"
        )
        res = state["meter"].add(llm.generate(prompt, system=SYSTEM, json_out=True))
        data = res.json()
        grounded = bool(data.get("grounded", data.get("caliper") == "grounded"))
        unsupported = data.get("unsupported") or []
        if not grounded:
            return {
                "grounded": False,
                "unsupported": unsupported,
                "outcome": "refused_ungrounded",
                "answer": (
                    "The retrieved documents do not fully support an answer to this "
                    "question, so no answer is given. Unsupported points: "
                    + "; ".join(unsupported[:5])
                    if unsupported
                    else "The retrieved documents do not fully support an answer."
                ),
                "citations": [],
            }
        return {"grounded": True, "unsupported": [], "outcome": "answered"}

    @_timed("no_evidence")
    def no_evidence(state: GraphState) -> dict:
        return {
            "outcome": "refused_no_evidence",
            "answer": (
                "No passage in the ingested documents answers this. Rather than guess, "
                "this service refuses. Try naming the scheme explicitly, or ingest the "
                "document that covers it."
            ),
            "citations": [],
        }

    return {
        "route": route,
        "retrieve": retrieve,
        "grade": grade,
        "rewrite": rewrite,
        "generate": generate,
        "verify": verify,
        "no_evidence": no_evidence,
    }