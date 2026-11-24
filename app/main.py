from __future__ import annotations

import json
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import get_pricing, get_settings
from .graph.build import build_agent_graph, build_graph
from .llm import Meter, get_llm
from .models import AskRequest, AskResponse, Usage
from .observability import Recorder
from .store import HybridStore

_state: dict = {}


def init(llm=None, store=None, enable_verify: bool = True) -> None:
    """Build the service state. Arguments exist so tests can inject the offline
    stub and an in-memory store without a running Qdrant or an API key."""
    s = get_settings()
    llm = llm or get_llm()
    store = store if store is not None else HybridStore(llm)
    _state.clear()
    _state.update(
        settings=s,
        llm=llm,
        store=store,
        graph_linear=build_graph(llm, store, enable_verify=enable_verify),
        graph_agent=build_agent_graph(llm, store, enable_verify=enable_verify, max_steps=s.max_steps),
        recorder=Recorder(trace_path=s.trace_path),
        ready=False,
    )
    try:
        n = store.load_lexical_index()
        _state["chunks"] = n
        _state["ready"] = n > 0
    except Exception as exc:  # the service still starts; /healthz reports why
        _state["startup_error"] = f"{type(exc).__name__}: {exc}"


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not _state:  # tests call init() themselves before constructing the client
        init()
    yield


app = FastAPI(
    title="Caliper",
    version="0.2.0",
    description=(
        "A tool-using agent that answers from ingested documents, cites every claim, "
        "verifies its own answer before returning it, and reports what the answer cost.\n\n"
        "**Not an official government service.** Independent engineering project, not "
        "affiliated with or endorsed by any government department. Answers come from "
        "ingested documents that may be outdated or incomplete, and are not legal, "
        "financial or benefits advice. Verify everything on the official portal before "
        "acting on it. Do not send Aadhaar numbers, bank details or any personal "
        "identifier to this service."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev convenience; narrow this before any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


def _graph(mode: str):
    return _state["graph_agent"] if mode == "agent" else _state["graph_linear"]


def _require_ready() -> None:
    if not _state.get("graph_agent"):
        raise HTTPException(503, "service not initialised")
    if not _state.get("ready"):
        raise HTTPException(
            503,
            "no documents indexed — run `python -m app.ingest docs/` first "
            f"(startup_error: {_state.get('startup_error')})",
        )


@app.get("/healthz")
def healthz() -> dict:
    s = _state.get("settings")
    pricing = get_pricing()
    return {
        "status": "ok" if _state.get("ready") else "degraded",
        "ready": bool(_state.get("ready")),
        "indexed_chunks": _state.get("chunks", 0),
        "offline_mode": bool(s and s.is_offline),
        "model": getattr(_state.get("llm"), "model", None),
        "max_steps": getattr(s, "max_steps", None),
        "pricing_verified": pricing.verified,
        "startup_error": _state.get("startup_error"),
    }


@app.get("/metrics")
def metrics() -> dict:
    rec: Recorder | None = _state.get("recorder")
    return rec.snapshot() if rec else {"requests": 0}


@app.get("/documents")
def documents() -> dict:
    """What the agent can actually see. An empty list here explains every refusal."""
    store = _state.get("store")
    cache = getattr(store, "_cache", {}) or {}
    by_source: dict[str, int] = {}
    for chunk in cache.values():
        by_source[chunk.source] = by_source.get(chunk.source, 0) + 1
    return {
        "documents": [{"source": k, "chunks": v} for k, v in sorted(by_source.items())],
        "total_chunks": sum(by_source.values()),
    }


def _finalise(req: AskRequest, final: dict, meter: Meter, latency: float, rid: str) -> AskResponse:
    cost, reason = meter.cost_usd()
    secs = latency / 1000.0
    usage = Usage(
        tokens_in=meter.tokens_in,
        tokens_out=meter.tokens_out,
        llm_calls=meter.calls,
        cost_usd=cost,
        cost_unconfigured_reason=reason,
        tokens_per_sec=round(meter.tokens_out / secs, 2) if secs > 0 else None,
    )
    return AskResponse(
        question=req.question,
        outcome=final.get("outcome", "refused_no_evidence"),
        answer=final.get("answer", ""),
        citations=final.get("citations", []),
        grounded=final.get("grounded"),
        rewrites=final.get("rewrites", 0),
        retrieved_count=len(final.get("retrieved", [])),
        relevant_count=len(final.get("relevant", [])),
        latency_ms=latency,
        usage=usage,
        timings=final.get("timings", []) if req.trace else [],
        steps=final.get("steps", []),
        tools_used=final.get("tools_used", []),
        mode=req.mode,
        request_id=rid,
    )


def _record(rec: Recorder, req: AskRequest, resp: AskResponse, meter: Meter, final: dict) -> None:
    rec.record(
        {
            "request_id": resp.request_id,
            "ts": time.time(),
            "question": req.question,
            "mode": req.mode,
            "outcome": resp.outcome,
            "grounded": resp.grounded,
            "tools_used": resp.tools_used,
            "steps": len(resp.steps),
            "retrieved": resp.retrieved_count,
            "relevant": resp.relevant_count,
            "latency_ms": resp.latency_ms,
            "tokens_in": meter.tokens_in,
            "tokens_out": meter.tokens_out,
            "llm_calls": meter.calls,
            "cost_usd": resp.usage.cost_usd,
            "citations": [c.model_dump() for c in resp.citations],
            "timings": [t.model_dump() for t in final.get("timings", [])],
        }
    )


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    _require_ready()
    rid = uuid.uuid4().hex[:12]
    meter = Meter()
    t0 = time.perf_counter()
    final = _graph(req.mode).invoke(
        {"question": req.question, "rewrites": 0, "timings": [], "meter": meter}
    )
    latency = round((time.perf_counter() - t0) * 1000, 2)
    resp = _finalise(req, final, meter, latency, rid)
    _record(_state["recorder"], req, resp, meter, final)
    return resp


@app.post("/ask/stream")
def ask_stream(req: AskRequest):
    """Server-sent events, one per graph node as it completes.

    The agent's tool calls arrive as individual `step` events so the UI can show
    the loop happening instead of a spinner. The final `done` event carries the
    same payload as POST /ask.
    """
    _require_ready()
    rid = uuid.uuid4().hex[:12]
    meter = Meter()
    graph = _graph(req.mode)

    def sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

    def gen():
        t0 = time.perf_counter()
        merged: dict = {}
        emitted = 0
        yield sse("start", {"request_id": rid, "mode": req.mode, "question": req.question})
        try:
            for update in graph.stream(
                {"question": req.question, "rewrites": 0, "timings": [], "meter": meter}
            ):
                for node, payload in update.items():
                    if not isinstance(payload, dict):
                        continue
                    merged.update(payload)
                    yield sse("node", {"node": node})
                    for step in payload.get("steps", [])[emitted:]:
                        emitted += 1
                        yield sse("step", step)
                    if payload.get("answer") and node in ("generate", "answer"):
                        yield sse(
                            "draft",
                            {
                                "answer": payload["answer"],
                                "citations": [c.model_dump() for c in payload.get("citations", [])],
                            },
                        )
            latency = round((time.perf_counter() - t0) * 1000, 2)
            resp = _finalise(req, merged, meter, latency, rid)
            _record(_state["recorder"], req, resp, meter, merged)
            yield sse("done", resp.model_dump())
        except Exception as exc:  # never leave the client hanging on an open stream
            yield sse("error", {"error": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
