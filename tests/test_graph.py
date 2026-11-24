"""End-to-end graph and API tests, run entirely offline.

No API key, no network, no Qdrant. The offline stub in app/llm.py is steered by
two words in the question ('offtopic', 'ungrounded') so every branch of the
graph is exercised deterministically.
"""

import os

import pytest

os.environ["OFFLINE"] = "1"

from app import main  # noqa: E402
from app.graph.build import build_graph  # noqa: E402
from app.llm import Meter, OfflineLLM  # noqa: E402
from app.store import InMemoryStore  # noqa: E402
from tests.fixtures import fixture_chunks  # noqa: E402


@pytest.fixture
def llm():
    return OfflineLLM()


@pytest.fixture
def store(llm):
    return InMemoryStore(llm, fixture_chunks())


def run(graph, question: str) -> dict:
    return graph.invoke({"question": question, "rewrites": 0, "timings": [], "meter": Meter()})


class TestGraphPaths:
    def test_answered_path_produces_citations(self, llm, store):
        out = run(build_graph(llm, store), "What is the benefit amount under FFSS?")
        assert out["outcome"] == "answered"
        assert out["grounded"] is True
        assert out["citations"], "an answered response must carry at least one citation"

    def test_out_of_scope_is_refused_before_retrieval(self, llm, store):
        out = run(build_graph(llm, store), "offtopic question about football scores")
        assert out["outcome"] == "refused_out_of_scope"
        assert out.get("retrieved") is None
        assert out["citations"] == [] if "citations" in out else True

    def test_ungrounded_draft_is_refused_not_returned(self, llm, store):
        out = run(build_graph(llm, store), "ungrounded claim about FFSS instalments")
        assert out["outcome"] == "refused_ungrounded"
        assert out["grounded"] is False
        assert out["citations"] == []

    def test_no_relevant_evidence_refuses_after_bounded_rewrites(self, llm, store):
        out = run(build_graph(llm, store), "noevidence about an unlisted scheme")
        assert out["outcome"] == "refused_no_evidence"
        assert out["rewrites"] == 2, "rewrite loop must stop at MAX_REWRITES, not spin"

    def test_rewrite_loop_is_bounded(self, llm, store):
        out = run(build_graph(llm, store), "noevidence probe")
        rewrite_calls = [t for t in out["timings"] if t.node == "rewrite"]
        assert len(rewrite_calls) == 2

    def test_verify_can_be_disabled_for_ablation(self, llm, store):
        out = run(build_graph(llm, store, enable_verify=False), "ungrounded claim about FFSS")
        assert out["outcome"] == "answered", "ablation path must skip the groundedness gate"
        assert out["grounded"] is None


class TestInstrumentation:
    def test_every_node_reports_timing(self, llm, store):
        out = run(build_graph(llm, store), "What documents are required for FFSS?")
        nodes = [t.node for t in out["timings"]]
        assert nodes == ["route", "retrieve", "grade", "generate", "verify"]
        assert all(t.ms >= 0 for t in out["timings"])

    def test_token_usage_is_attributed_per_node(self, llm, store):
        out = run(build_graph(llm, store), "What is the FSMG income limit?")
        charged = [t for t in out["timings"] if t.tokens_in > 0]
        assert len(charged) >= 3, "route, grade, generate and verify all call the model"

    def test_meter_total_equals_sum_of_node_usage(self, llm, store):
        state = {"question": "FFSS eligibility", "rewrites": 0, "timings": [], "meter": Meter()}
        out = build_graph(llm, store).invoke(state)
        assert sum(t.tokens_in for t in out["timings"]) == state["meter"].tokens_in


class TestRetrieval:
    def test_lexical_term_is_retrievable(self, store):
        hits = store.search("2 hectares cultivable land")
        assert hits
        assert any("hectare" in h.chunk.text.lower() for h in hits)

    def test_results_are_ranked_by_fused_score(self, store):
        hits = store.search("instalments bank account")
        scores = [h.fused_score for h in hits]
        assert scores == sorted(scores, reverse=True)

    def test_empty_corpus_returns_no_hits(self, llm):
        assert InMemoryStore(llm, []).search("anything") == []


class TestAPI:
    @pytest.fixture
    def client(self, llm, store, tmp_path):
        from fastapi.testclient import TestClient

        main.init(llm=llm, store=store)
        main._state["recorder"].__init__(trace_path=str(tmp_path / "t.jsonl"))
        return TestClient(main.app)

    def test_healthz_reports_ready_and_offline(self, client):
        body = client.get("/healthz").json()
        assert body["ready"] is True
        assert body["offline_mode"] is True
        assert body["indexed_chunks"] > 0

    def test_ask_returns_answer_and_usage(self, client):
        body = client.post("/ask", json={"question": "What is the FFSS benefit?"}).json()
        assert body["outcome"] == "answered"
        assert body["usage"]["llm_calls"] >= 3
        assert body["latency_ms"] > 0
        assert body["request_id"]

    def test_cost_is_null_with_a_reason_when_pricing_unverified(self, client):
        body = client.post("/ask", json={"question": "What is the FFSS benefit?"}).json()
        assert body["usage"]["cost_usd"] is None
        assert "pricing.yaml" in body["usage"]["cost_unconfigured_reason"]

    def test_trace_is_opt_in(self, client):
        off = client.post("/ask", json={"question": "FFSS benefit?"}).json()
        on = client.post("/ask", json={"question": "FFSS benefit?", "trace": True}).json()
        assert off["timings"] == [] and len(on["timings"]) >= 4

    def test_metrics_aggregate_after_requests(self, client):
        for q in ("FFSS benefit?", "FSMG attendance rule?", "offtopic thing"):
            client.post("/ask", json={"question": q})
        m = client.get("/metrics").json()
        assert m["requests"] == 3
        assert m["latency_ms"]["p95"] is not None
        assert m["cost_usd"]["note"].startswith("unconfigured")
        assert 0.0 <= m["refusal_rate"] <= 1.0
        assert sum(m["outcomes"].values()) == 3

    def test_short_question_is_rejected_by_validation(self, client):
        assert client.post("/ask", json={"question": "hi"}).status_code == 422
