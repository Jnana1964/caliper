from pathlib import Path

import pytest
import yaml

from app.config import Pricing
from app.llm import LLMResult, Meter, OfflineLLM
from app.observability import percentile
from app.store import chunk_text, rrf, tokenize


class TestChunking:
    def test_short_text_is_one_chunk(self):
        chunks = chunk_text("A short paragraph.", "s.txt", "s")
        assert len(chunks) == 1
        assert chunks[0].text == "A short paragraph."

    def test_empty_text_yields_nothing(self):
        assert chunk_text("   \n\n  ", "s.txt", "s") == []

    def test_long_text_splits_and_respects_target(self):
        body = "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(20))
        chunks = chunk_text(body, "s.txt", "s", target=800, overlap=100)
        assert len(chunks) > 1
        # overlap means a chunk can exceed target by at most the overlap it carries
        assert all(len(c.text) <= 800 + 100 + 80 for c in chunks)

    def test_overlap_carries_context_forward(self):
        body = "\n\n".join(f"Clause {i} " + "x" * 300 for i in range(6))
        chunks = chunk_text(body, "s.txt", "s", target=600, overlap=120)
        assert len(chunks) >= 2
        tail = chunks[0].text[-60:]
        assert tail in chunks[1].text

    def test_ids_are_deterministic_across_runs(self):
        a = chunk_text("Stable content here.", "s.txt", "s", page=3)
        b = chunk_text("Stable content here.", "s.txt", "s", page=3)
        assert [c.chunk_id for c in a] == [c.chunk_id for c in b]

    def test_ids_differ_across_documents(self):
        a = chunk_text("Same text.", "one.txt", "one")
        b = chunk_text("Same text.", "two.txt", "two")
        assert a[0].chunk_id != b[0].chunk_id

    def test_tokenize_strips_punctuation_and_case(self):
        assert tokenize("SC/ST households, ₹6,000!") == ["sc", "st", "households", "6", "000"]


class TestRRF:
    def test_agreement_at_rank_one_beats_either_alone(self):
        s = rrf(["a", "b"], ["a", "c"], k=60)
        assert s["a"] > s["b"] and s["a"] > s["c"]

    def test_exact_formula(self):
        s = rrf(["a"], ["b"], k=60)
        assert s["a"] == pytest.approx(1 / 61)
        assert s["b"] == pytest.approx(1 / 61)

    def test_doc_in_both_lists_sums_both_contributions(self):
        s = rrf(["x", "y"], ["y"], k=10)
        assert s["y"] == pytest.approx(1 / 12 + 1 / 11)

    def test_empty_rankings_give_empty_scores(self):
        assert rrf([], [], k=60) == {}

    def test_k_damps_rank_differences(self):
        tight = rrf(["a", "b"], [], k=1000)
        loose = rrf(["a", "b"], [], k=1)
        assert (tight["a"] - tight["b"]) < (loose["a"] - loose["b"])


class TestCost:
    def _pricing(self, tmp_path: Path, **over) -> Pricing:
        data = {
            "verified": True,
            "source_url": "https://example.invalid",
            "verified_on": "2026-01-01",
            "models": {"m": {"input_per_mtok": 1.0, "output_per_mtok": 10.0}},
        }
        data.update(over)
        p = tmp_path / "pricing.yaml"
        p.write_text(yaml.safe_dump(data))
        return Pricing(p)

    def test_unverified_pricing_returns_none_not_zero(self, tmp_path):
        pr = self._pricing(tmp_path, verified=False)
        assert pr.cost_usd("m", 1_000_000, 1_000_000) is None

    def test_known_model_computes_exactly(self, tmp_path):
        pr = self._pricing(tmp_path)
        assert pr.cost_usd("m", 2_000_000, 500_000) == pytest.approx(2.0 + 5.0)

    def test_unknown_model_returns_none(self, tmp_path):
        assert self._pricing(tmp_path).cost_usd("other", 100, 100) is None

    def test_null_rate_returns_none(self, tmp_path):
        pr = self._pricing(tmp_path, models={"m": {"input_per_mtok": None, "output_per_mtok": 1.0}})
        assert pr.cost_usd("m", 100, 100) is None

    def test_meter_accumulates_across_calls(self):
        m = Meter()
        m.add(LLMResult("a", 10, 2, 1.0, "m"))
        m.add(LLMResult("b", 5, 3, 1.0, "m"))
        assert (m.tokens_in, m.tokens_out, m.calls) == (15, 5, 2)

    def test_meter_cost_is_none_with_a_reason_when_unconfigured(self):
        m = Meter()
        m.add(LLMResult("a", 10, 2, 1.0, "m"))
        cost, reason = m.cost_usd()
        assert cost is None and reason and "pricing.yaml" in reason


class TestPercentile:
    def test_empty_returns_none_not_zero(self):
        assert percentile([], 95) is None

    def test_p50_of_known_series(self):
        assert percentile([1, 2, 3, 4, 5], 50) == 3

    def test_p100_is_max(self):
        assert percentile([4, 1, 9, 2], 100) == 9

    def test_single_value(self):
        assert percentile([7.5], 95) == 7.5


class TestOfflineStub:
    def test_embeddings_are_deterministic_and_normalised(self):
        llm = OfflineLLM()
        a = llm.embed(["hello"], dim=64)[0]
        b = llm.embed(["hello"], dim=64)[0]
        assert a == b
        assert sum(v * v for v in a) == pytest.approx(1.0, rel=1e-6)

    def test_different_text_gives_different_vector(self):
        llm = OfflineLLM()
        assert llm.embed(["alpha"], dim=32)[0] != llm.embed(["beta"], dim=32)[0]
