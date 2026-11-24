from __future__ import annotations

from typing import TypedDict

from ..llm import Meter
from ..models import Citation, NodeTiming, Retrieved


class GraphState(TypedDict, total=False):
    question: str
    query: str  # current query; the rewrite node replaces this, never `question`
    rewrites: int
    retrieved: list[Retrieved]
    relevant: list[Retrieved]
    answer: str
    citations: list[Citation]
    grounded: bool | None
    unsupported: list[str]
    outcome: str
    timings: list[NodeTiming]
    meter: Meter
    # agent mode only
    steps: list[dict]
    tools_used: list[str]
