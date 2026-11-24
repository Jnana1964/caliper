from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gen_model: str = "gemini-2.5-flash"
    embed_model: str = "gemini-embedding-001"
    embed_dim: int = 768

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    collection: str = "schemes"

    top_k: int = 8
    rrf_k: int = 60
    max_rewrites: int = 2
    max_steps: int = 5

    offline: bool = False
    trace_path: str = "traces/trace.jsonl"

    @property
    def is_offline(self) -> bool:
        return self.offline or os.environ.get("OFFLINE") in {"1", "true", "True"}


class Pricing:
    """Token pricing loaded from config/pricing.yaml.

    Deliberately returns None for cost when the file has not been verified by a
    human against the official pricing page. A wrong cost number quoted with
    confidence is worse than an honest 'unconfigured'.
    """

    def __init__(self, path: Path | None = None) -> None:
        path = path or ROOT / "config" / "pricing.yaml"
        data = yaml.safe_load(path.read_text()) if path.exists() else {}
        self.verified: bool = bool(data.get("verified"))
        self.verified_on = data.get("verified_on")
        self.source_url = data.get("source_url")
        self.models: dict = data.get("models") or {}

    def cost_usd(self, model: str, tokens_in: int, tokens_out: int) -> float | None:
        if not self.verified:
            return None
        rates = self.models.get(model)
        if not rates:
            return None
        pin, pout = rates.get("input_per_mtok"), rates.get("output_per_mtok")
        if pin is None or pout is None:
            return None
        return round(tokens_in / 1e6 * float(pin) + tokens_out / 1e6 * float(pout), 8)


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_pricing() -> Pricing:
    return Pricing()
