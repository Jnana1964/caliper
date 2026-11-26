"""The ReAct loop: plan, act, observe, repeat — then answer and verify.

The difference from the linear graph is that nothing is hard-wired. The model
is shown the toolbox and decides, each turn, which tool to call and with what
arguments. It sees the result and decides again. The loop ends when it calls
`finish`, when the step budget runs out, or when it has gathered nothing usable.

The step budget is not decoration. An agent with an unbounded loop and a paid
model behind it is a bill, and the first thing a reviewer looks for.
"""

from __future__ import annotations

import json
import time

from ..models import Citation, NodeTiming, Retrieved
from ..models import Chunk
from ..tools import build_toolbox, run_tool, toolbox_spec
from .nodes import SYSTEM, _cited_markers, _format_excerpts
from .state import GraphState

MAX_STEPS_DEFAULT = 5


def _timing(node: str, t0: float, meter, before: tuple[int, int]) -> NodeTiming:
    return NodeTiming(
        node=node,
        ms=round((time.perf_counter() - t0) * 1000, 2),
        tokens_in=meter.tokens_in - before[0],
        tokens_out=meter.tokens_out - before[1],
    )


def make_agent_nodes(llm, store, max_steps: int = MAX_STEPS_DEFAULT):
    toolbox = build_toolbox(store)
    spec = toolbox_spec(toolbox)

    def reason_act(state: GraphState) -> dict:
        """One full plan/act/observe loop, run inside a single graph node.

        Kept as one node so the whole loop shares a step budget and a scratchpad;
        every individual tool call is still recorded in `steps` and streamed to
        the UI, so nothing is hidden.
        """
        meter = state["meter"]
        steps: list[dict] = []
        scratch: list[str] = []
        seen: dict[str, Retrieved] = {}
        timings: list[NodeTiming] = list(state.get("timings", []))

        for step_no in range(1, max_steps + 1):
            t0 = time.perf_counter()
            before = (meter.tokens_in, meter.tokens_out)

            history = "\n\n".join(scratch) if scratch else "(nothing gathered yet)"
            prompt = (
                "#PLAN\nYou are answering a question using tools. Decide the single next "
                "tool call that gets you closest to a well-evidenced answer.\n\n"
                f"TOOLS:\n{spec}\n\n"
                'Reply as JSON: {"thought": "<one sentence>", "tool": "<name>", '
                '"args": {<arguments>}}\n'
                "Call finish as soon as you have enough evidence, or when it is clear the "
                "documents cannot answer. Do not repeat a search that already returned "
                "nothing useful.\n\n"
                f"QUESTION: {state['question']}\n\n"
                f"WHAT YOU HAVE SO FAR:\n{history}"
            )
            res = meter.add(llm.generate(prompt, system=SYSTEM, json_out=True))
            plan = res.json()
            tool_name = (plan.get("tool") or "finish").strip()
            args = plan.get("args") or {}
            thought = (plan.get("thought") or "").strip()

            observation = run_tool(toolbox, tool_name, args)

            # fold any retrieved passages into the evidence set
            for hit in observation.get("hits", []) or []:
                chunk = Chunk(
                    chunk_id=hit["chunk_id"],
                    doc_id=hit.get("source", ""),
                    source=hit.get("source", ""),
                    page=hit.get("page"),
                    text=hit.get("text", ""),
                )
                seen.setdefault(
                    chunk.chunk_id,
                    Retrieved(chunk=chunk, fused_score=float(hit.get("score") or 0.0), relevant=True),
                )

            summary = json.dumps(observation)[:1200]
            scratch.append(f"step {step_no}: called {tool_name}({args}) -> {summary}")
            steps.append(
                {
                    "step": step_no,
                    "thought": thought,
                    "tool": tool_name,
                    "args": args,
                    "ok": bool(observation.get("ok")),
                    "error": observation.get("error"),
                    "result_count": observation.get("count")
                    or len(observation.get("hits", []) or []),
                    "result": observation.get("result"),
                }
            )
            timings.append(_timing(f"step{step_no}:{tool_name}", t0, meter, before))

            if tool_name == "finish" or observation.get("finished"):
                break

        evidence = list(seen.values())
        return {
            "steps": steps,
            "retrieved": evidence,
            "relevant": evidence,
            "tools_used": [s["tool"] for s in steps],
            "timings": timings,
        }

    def answer(state: GraphState) -> dict:
        t0 = time.perf_counter()
        meter = state["meter"]
        before = (meter.tokens_in, meter.tokens_out)
        items = state.get("relevant") or []

        if not items:
            return {
                "outcome": "refused_no_evidence",
                "answer": (
                    "The agent gathered no usable evidence from the ingested documents, "
                    "so it is not answering. Try naming the scheme explicitly, or ingest "
                    "the document that covers this."
                ),
                "citations": [],
                "timings": state.get("timings", []) + [_timing("answer", t0, meter, before)],
            }

        prompt = (
            "Answer the question using only the excerpts. Cite every factual claim inline "
            "with its marker, like [S1]. If the excerpts do not settle part of the question, "
            "say so plainly instead of filling the gap.\n\n"
            f"QUESTION: {state['question']}\n\n{_format_excerpts(items)}"
        )
        res = meter.add(llm.generate(prompt, system=SYSTEM))
        text = res.text.strip()
        cites = [
            Citation(marker=f"S{i}", source=r.chunk.source, page=r.chunk.page, chunk_id=r.chunk.chunk_id)
            for i, r in enumerate(items, start=1)
                        if i in _cited_markers(text)
        ]
        return {
            "answer": text,
            "citations": cites,
            "timings": state.get("timings", []) + [_timing("answer", t0, meter, before)],
        }

    return {"reason_act": reason_act, "answer": answer}
