"""Graph assembly.

    route ──out of scope──────────────────────────────────────► END
      │ in scope
      ▼
    retrieve ──► grade ──┬── relevant found ──► generate ──► verify ──► END
                         │                                      (refuses if ungrounded)
                         ├── nothing relevant, retries left ──► rewrite ──┐
                         │                                                │
                         └── nothing relevant, retries spent ─► no_evidence ──► END
                                                                          │
                              ◄───────────────────────────────────────────┘

Two reflection points (grade, verify) and a bounded rewrite loop. The bound
matters: an unbounded retry loop is how an agent quietly burns a token budget.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..config import get_settings
from .agent import make_agent_nodes
from .nodes import make_nodes
from .state import GraphState


def build_agent_graph(llm, store, enable_verify: bool = True, max_steps: int = 5):
    """Agent mode: the model picks its own tools each turn.

        reason_act (plan -> act -> observe, bounded)  ->  answer  ->  verify  -> END

    Compare against build_graph() on the same eval set: that comparison is the
    honest way to find out whether letting the model choose actually helps, or
    whether a fixed pipeline wins on this corpus.
    """
    n = make_agent_nodes(llm, store, max_steps=max_steps)
    v = make_nodes(llm, store)

    g = StateGraph(GraphState)
    g.add_node("reason_act", n["reason_act"])
    g.add_node("answer", n["answer"])
    g.add_edge(START, "reason_act")
    g.add_edge("reason_act", "answer")

    if enable_verify:
        g.add_node("verify", v["verify"])
        g.add_conditional_edges(
            "answer",
            lambda s: END if s.get("outcome", "").startswith("refused") else "verify",
            {END: END, "verify": "verify"},
        )
        g.add_edge("verify", END)
    else:
        g.add_node("mark_answered", lambda s: {"outcome": s.get("outcome") or "answered", "grounded": None})
        g.add_edge("answer", "mark_answered")
        g.add_edge("mark_answered", END)

    return g.compile()


def build_graph(llm, store, enable_verify: bool = True):
    n = make_nodes(llm, store)
    max_rewrites = get_settings().max_rewrites

    g = StateGraph(GraphState)
    for name in ("route", "retrieve", "grade", "rewrite", "generate", "verify", "no_evidence"):
        g.add_node(name, n[name])

    g.add_edge(START, "route")
    g.add_conditional_edges(
        "route",
        lambda s: END if s.get("outcome") == "refused_out_of_scope" else "retrieve",
        {END: END, "retrieve": "retrieve"},
    )
    g.add_edge("retrieve", "grade")

    def after_grade(s: GraphState) -> str:
        if s.get("relevant"):
            return "generate"
        if s.get("rewrites", 0) < max_rewrites:
            return "rewrite"
        return "no_evidence"

    g.add_conditional_edges(
        "grade",
        after_grade,
        {"generate": "generate", "rewrite": "rewrite", "no_evidence": "no_evidence"},
    )
    g.add_edge("rewrite", "retrieve")
    g.add_edge("no_evidence", END)

    if enable_verify:
        g.add_edge("generate", "verify")
        g.add_edge("verify", END)
    else:
        # Ablation path for the eval harness: skip the groundedness gate so the
        # two runs can be compared. Never used by the served API.
        g.add_node("mark_answered", lambda s: {"outcome": "answered", "grounded": None})
        g.add_edge("generate", "mark_answered")
        g.add_edge("mark_answered", END)

    return g.compile()
