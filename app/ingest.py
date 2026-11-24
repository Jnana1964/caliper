"""Ingest PDFs and text files into the vector store.

    python -m app.ingest docs/
    python -m app.ingest docs/pmkisan-guidelines.pdf --dry-run

Reports how many pages produced no extractable text. That number matters: many
Indian government PDFs are scans, and a silent zero-text page is the difference
between "the system refused" and "the system never had the document".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import get_settings
from .llm import get_llm
from .models import Chunk
from .store import HybridStore, chunk_text


def read_pdf(path: Path) -> list[tuple[int, str]]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return [(i, (pg.extract_text() or "").strip()) for i, pg in enumerate(reader.pages, start=1)]


def collect(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(
        p for p in target.rglob("*") if p.suffix.lower() in {".pdf", ".txt", ".md"}
    )


def build_chunks(paths: list[Path]) -> tuple[list[Chunk], int, int]:
    chunks: list[Chunk] = []
    empty_pages = 0
    total_pages = 0
    for path in paths:
        doc_id = path.stem
        if path.suffix.lower() == ".pdf":
            for page_no, text in read_pdf(path):
                total_pages += 1
                if not text:
                    empty_pages += 1
                    continue
                chunks += chunk_text(text, source=path.name, doc_id=doc_id, page=page_no)
        else:
            total_pages += 1
            text = path.read_text(encoding="utf-8", errors="ignore")
            if not text.strip():
                empty_pages += 1
                continue
            chunks += chunk_text(text, source=path.name, doc_id=doc_id, page=None)
    return chunks, empty_pages, total_pages


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest documents into the vector store")
    ap.add_argument("path", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="chunk and report, do not embed")
    args = ap.parse_args()

    if not args.path.exists():
        print(f"error: {args.path} does not exist", file=sys.stderr)
        return 2

    paths = collect(args.path)
    if not paths:
        print(f"error: no .pdf/.txt/.md files under {args.path}", file=sys.stderr)
        return 2

    chunks, empty_pages, total_pages = build_chunks(paths)
    sizes = [len(c.text) for c in chunks] or [0]
    print(f"files          : {len(paths)}")
    print(f"pages          : {total_pages}")
    print(f"pages no text  : {empty_pages}" + ("   <-- likely scanned, needs OCR" if empty_pages else ""))
    print(f"chunks         : {len(chunks)}")
    print(f"chunk chars    : min {min(sizes)} / mean {sum(sizes)//len(sizes)} / max {max(sizes)}")

    if args.dry_run:
        print("\ndry run, nothing embedded")
        return 0
    if not chunks:
        print("nothing to embed", file=sys.stderr)
        return 1

    s = get_settings()
    store = HybridStore(get_llm())
    n = store.upsert(chunks)
    print(f"\nembedded and upserted {n} chunks into collection {s.collection!r} at {s.qdrant_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
