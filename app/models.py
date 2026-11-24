from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    source: str
    page: int | None = None
    text: str


class Retrieved(BaseModel):
    chunk: Chunk
    dense_rank: int | None = None
    bm25_rank: int | None = None
    fused_score: float
    relevant: bool | None = None  # filled by the grade node


class Citation(BaseModel):
    marker: str  # e.g. "S1"
    source: str
    page: int | None = None
    chunk_id: str


class NodeTiming(BaseModel):
    node: str
    ms: float
    tokens_in: int = 0
    tokens_out: int = 0


class Usage(BaseModel):
    tokens_in: int = 0
    tokens_out: int = 0
    llm_calls: int = 0
    cost_usd: float | None = None
    cost_unconfigured_reason: str | None = None
    tokens_per_sec: float | None = None


class AgentStep(BaseModel):
    step: int
    thought: str = ""
    tool: str
    args: dict = {}
    ok: bool = True
    error: str | None = None
    result_count: int | None = None
    result: float | str | None = None


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    trace: bool = False
    mode: Literal["agent", "linear"] = "agent"


class AskResponse(BaseModel):
    question: str
    outcome: Literal["answered", "refused_out_of_scope", "refused_no_evidence", "refused_ungrounded"]
    answer: str
    citations: list[Citation] = []
    grounded: bool | None = None
    rewrites: int = 0
    retrieved_count: int = 0
    relevant_count: int = 0
    latency_ms: float = 0.0
    usage: Usage = Usage()
    timings: list[NodeTiming] = []
    steps: list[AgentStep] = []
    tools_used: list[str] = []
    mode: str = "agent"
    request_id: str = ""
