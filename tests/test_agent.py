"""Agent-mode tests: the toolbox, the bounded loop, and the streaming endpoint."""

import os

import pytest

os.environ["OFFLINE"] = "1"

from app import main  # noqa: E402
from app.graph.build import build_agent_graph  # noqa: E402
from app.llm import Meter, OfflineLLM  # noqa: E402
from app.store import InMemoryStore  # noqa: E402
from app.tools import build_toolbox, run_tool, safe_eval, toolbox_spec  # noqa: E402
from tests.fixtures import fixture_chunks  # noqa: E402


@pytest.fixture
def llm():
    return OfflineLLM()


@pytest.fixture
def store(llm):
    return InMemoryStore(llm, fixture_chunks())


@pytest.fixture
def toolbox(store):
    return build_toolbox(store)


class TestSafeEval:
    def test_arithmetic(self):
        assert safe_eval("2 + 3 * 4") == 14
        assert safe_eval("(450000 - 400000) / 1000") == 50

    def test_unary_minus(self):
        assert safe_eval("-5 + 2") == -3

    def test_rejects_function_calls(self):
        with pytest.raises(ValueError):
            safe_eval("__import__('os').system('ls')")

    def test_rejects_names(self):
        with pytest.raises(ValueError):
            safe_eval("x + 1")

    def test_rejects_strings(self):
        with pytest.raises(ValueError):
            safe_eval("'a' * 10")

    def test_rejects_booleans(self):
        with pytest.raises(ValueError):
            safe_eval("True + 1")


class TestToolbox:
    def test_spec_lists_every_tool(self, toolbox):
        spec = toolbox_spec(toolbox)
        for name in ("search_documents", "lookup_number", "calculate", "current_date", "finish"):
            assert name in spec

    def test_search_returns_hits(self, toolbox):
        out = run_tool(toolbox, "search_documents", {"query": "hectares of cultivable land"})
        assert out["ok"] and out["count"] > 0
        assert "chunk_id" in out["hits"][0]

    def test_lookup_number_prefers_passages_with_figures(self, toolbox):
        out = run_tool(toolbox, "lookup_number", {"query": "benefit amount"})
        assert out["ok"]
        assert out["hits"][0]["has_figures"] is True

    def test_calculate_ok(self, toolbox):
        assert run_tool(toolbox, "calculate", {"expression": "9000 / 3"})["result"] == 3000

    def test_calculate_failure_is_returned_not_raised(self, toolbox):
        out = run_tool(toolbox, "calculate", {"expression": "open('x')"})
        assert out["ok"] is False and "error" in out

    def test_current_date(self, toolbox):
        out = run_tool(toolbox, "current_date", {})
        assert out["ok"] and out["today"].count("-") == 2

    def test_unknown_tool_is_handled(self, toolbox):
        out = run_tool(toolbox, "launch_missiles", {})
        assert out["ok"] is False and "no such tool" in out["error"]

    def test_missing_argument_is_reported(self, toolbox):
        out = run_tool(toolbox, "calculate", {})
        assert out["ok"] is False and "missing arguments" in out["error"]

    def test_extra_arguments_are_dropped(self, toolbox):
        out = run_tool(toolbox, "calculate", {"expression": "1+1", "rm": "-rf"})
        assert out["ok"] and out["result"] == 2


def run(graph, q):
    return graph.invoke({"question": q, "rewrites": 0, "timings": [], "meter": Meter()})


class TestAgentLoop:
    def test_agent_selects_tools_and_answers(self, llm, store):
        out = run(build_agent_graph(llm, store), "What is the FFSS benefit amount?")
        assert out["outcome"] == "answered"
        assert out["tools_used"][0] == "search_documents"
        assert out["tools_used"][-1] == "finish"
        assert out["citations"]

    def test_every_step_is_recorded(self, llm, store):
        out = run(build_agent_graph(llm, store), "What documents are required for FFSS?")
        assert len(out["steps"]) >= 2
        first = out["steps"][0]
        assert first["step"] == 1 and first["tool"] and first["ok"] is True

    def test_loop_is_bounded_by_max_steps(self, llm, store):
        class NeverFinishes(OfflineLLM):
            def generate(self, prompt, system=None, **kw):
                if "#PLAN" in prompt:
                    import json as _j

                    from app.llm import LLMResult

                    body = _j.dumps({"thought": "again", "tool": "search_documents", "args": {"query": "x"}})
                    return LLMResult(body, 10, 5, 0.1, self.model)
                return super().generate(prompt, system=system, **kw)

        out = run(build_agent_graph(NeverFinishes(), store, max_steps=3), "endless question")
        assert len(out["steps"]) == 3, "a runaway agent must stop at MAX_STEPS"

    def test_tool_timings_are_attributed_per_step(self, llm, store):
        out = run(build_agent_graph(llm, store), "FFSS land limit?")
        step_timings = [t for t in out["timings"] if t.node.startswith("step")]
        assert len(step_timings) == len(out["steps"])

    def test_verify_still_gates_the_answer(self, llm, store):
        out = run(build_agent_graph(llm, store), "ungrounded claim about FFSS")
        assert out["outcome"] == "refused_ungrounded"
        assert out["citations"] == []

    def test_ablation_path_skips_verify(self, llm, store):
        out = run(build_agent_graph(llm, store, enable_verify=False), "ungrounded claim about FFSS")
        assert out["outcome"] == "answered" and out["grounded"] is None

    def test_empty_corpus_refuses_instead_of_inventing(self, llm):
        out = run(build_agent_graph(llm, InMemoryStore(llm, [])), "anything at all")
        assert out["outcome"] == "refused_no_evidence"
        assert out["answer"]


class TestAgentAPI:
    @pytest.fixture
    def client(self, llm, store, tmp_path):
        from fastapi.testclient import TestClient

        main.init(llm=llm, store=store)
        main._state["recorder"].__init__(trace_path=str(tmp_path / "t.jsonl"))
        return TestClient(main.app)

    def test_agent_is_the_default_mode(self, client):
        body = client.post("/ask", json={"question": "What is the FFSS benefit?"}).json()
        assert body["mode"] == "agent"
        assert body["tools_used"]

    def test_linear_mode_still_available(self, client):
        body = client.post("/ask", json={"question": "What is the FFSS benefit?", "mode": "linear"}).json()
        assert body["mode"] == "linear" and body["steps"] == []

    def test_documents_endpoint_lists_the_corpus(self, client):
        body = client.get("/documents").json()
        assert body["total_chunks"] > 0
        assert any(d["source"].endswith(".txt") for d in body["documents"])

    def test_stream_emits_steps_then_done(self, client):
        with client.stream("POST", "/ask/stream", json={"question": "FFSS benefit amount?"}) as r:
            assert r.status_code == 200
            events = [ln[7:] for ln in r.iter_lines() if ln.startswith("event: ")]
        assert events[0] == "start"
        assert "step" in events
        assert events[-1] == "done"

    def test_stream_reports_mode(self, client):
        with client.stream("POST", "/ask/stream", json={"question": "FFSS?", "mode": "linear"}) as r:
            text = "".join(r.iter_text())
        assert '"mode": "linear"' in text
