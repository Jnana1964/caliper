# Document sources

This repository ships **no scheme documents**. It ships the pipeline that
ingests them. Scheme rules and benefit amounts change, and a stale copy
committed to a Git repo is exactly the kind of confidently-wrong source this
project is built to avoid.

Download the PDFs you want to index into `docs/`, then run:

```bash
python -m app.ingest docs/
```

## Where to get them

Use the official portal for each scheme. Save the PDF with a filename that
makes the citation readable, for example `pmkisan-operational-guidelines.pdf`,
because that filename is what appears in every citation the service returns.

| Scheme | Official portal |
|---|---|
| PM-KISAN | pmkisan.gov.in |
| Ayushman Bharat PM-JAY | pmjay.gov.in |
| National Scholarship Portal | scholarships.gov.in |
| PM Awas Yojana (Gramin) | pmayg.nic.in |
| MGNREGA | nrega.nic.in |
| e-Shram | eshram.gov.in |

Record what you downloaded and when, below. A retrieval system is only as
current as its corpus, and the date is part of the answer.

| File | Scheme | Source URL | Downloaded on |
|---|---|---|---|
| | | | |

## A warning about scanned PDFs

Many Indian government PDFs are scans with no text layer. `app.ingest` reports
`pages no text` for exactly this reason — if that count is high, the documents
went in empty and every answer about them will be a refusal. Run OCR
(`ocrmypdf in.pdf out.pdf`) before ingesting those.

## Fictional documents in this repo

`tests/fixtures.py` contains two **invented** schemes used only by the test
suite, so the tests run without a real corpus. Their rules are made up. Never
quote them as if they described a real scheme.
