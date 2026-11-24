"""Run the whole API with no API key, no network and no Qdrant.

    python scripts/dev_offline.py

Uses the deterministic offline stub and the fictional fixture corpus from
tests/fixtures.py, so the UI and every endpoint work end to end on a fresh
clone. Nothing it answers means anything — the schemes are invented and the
model is a stub. It exists so you can see the interface before you have
documents, a key, or a vector store.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["OFFLINE"] = "1"

import uvicorn  # noqa: E402

from app import main  # noqa: E402
from app.llm import OfflineLLM  # noqa: E402
from app.store import InMemoryStore  # noqa: E402
from tests.fixtures import fixture_chunks  # noqa: E402


def build_app():
    llm = OfflineLLM()
    main.init(llm=llm, store=InMemoryStore(llm, fixture_chunks()))
    return main.app


if __name__ == "__main__":
    print("OFFLINE demo: stub model, fictional corpus. Answers mean nothing.")
    uvicorn.run(build_app(), host="127.0.0.1", port=int(os.environ.get("PORT", 8000)))
