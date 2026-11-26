# Document sources

This repository ships **no scheme documents**. It ships the pipeline that
ingests them. Scheme rules and benefit amounts change, and a stale copy
committed to a Git repo is exactly the kind of confidently wrong source this
project is built to avoid.

Download the PDFs into `docs/`, then run:

```bash
python -m app.ingest docs/
```

## The corpus these results were measured on

Six documents, 170 pages, 289 chunks. Every figure in the README was produced
against exactly this set. Download these six and you reproduce the corpus.

| File in `docs/` | Document | Source URL | Downloaded |
|---|---|---|---|
| `nsp-student-user-manual.pdf` | National Scholarship Portal, Student User Manual | https://scholarships.gov.in/public/FAQ/NSP_User_Manual_v1.0.pdf | 26 Nov 2026 |
| `top-class-education-sc.pdf` | Scheme of Top Class Education for Scheduled Caste Students, scheme guidelines, applicable from 2025 to 2026 | https://scholarships.gov.in/public/schemeGuidelines/Top_Class_Education_Scheme_2018.pdf | 26 Nov 2026 |
| `post-matric-disabilities.pdf` | Scholarships for Students with Disabilities, central sector umbrella scheme, effective 1 April 2022 | https://scholarships.gov.in/public/schemeGuidelines/DEPDGuidelines.pdf | 26 Nov 2026 |
| `csss-pmusp-guidelines.pdf` | Pradhan Mantri Uchchatar Shiksha Protsahan Yojana, scheme guidelines | https://scholarships.gov.in/public/schemeGuidelines/Guidelines_DOHE_CSSS.pdf | 26 Nov 2026 |
| `csss-faq.pdf` | Central Sector Scheme of Scholarship for College and University Students, frequently asked questions | https://scholarships.gov.in/public/schemeGuidelines/FAQ_DOHE_CSSS.pdf | 26 Nov 2026 |
| `aicte-scheme-guidelines.pdf` | AICTE scholarship scheme guidelines | https://scholarships.gov.in/public/schemeGuidelines/AICTE/AICTE_2013_G.pdf | 26 Nov 2026 |

Save each file under exactly that name. The filename is what appears in every
citation the service returns, so a careless name produces a useless citation.

One page of the 170 carries no extractable text and `app.ingest` reports it as
such. It is a layout page, not a rule page, and it is left as it is rather than
quietly patched, because a corpus you have measured is worth more than a corpus
you have tidied.

## Swapping in a different corpus

Nothing in the code is specific to scholarships. Point `docs/` at any set of
documents and the pipeline works, but two things must change with it, or your
numbers become fiction:

`eval/questions.yaml` is an answer key written by hand against these six
documents. It does not transfer.

The router prompt in `app/graph/nodes.py` describes the subject matter of the
corpus. A router told it is screening scholarship questions will refuse
everything about a corpus of something else.

## A warning about scanned PDFs

Many Indian government PDFs are scans with no text layer. `app.ingest` reports
`pages no text` for exactly this reason. If that count is high, the documents
went in empty and every answer about them will be a refusal. Check a PDF before
you keep it: open it, press Ctrl+F, search a word you can see. If nothing
highlights, it is a scan. Run `ocrmypdf in.pdf out.pdf` before ingesting it.

## Fictional documents in this repo

`tests/fixtures.py` contains two **invented** schemes used only by the test
suite, so the tests run without a real corpus. Their rules are made up. Never
quote them as if they described a real scheme.

## Attribution and status

These documents are published by departments of the Government of India and are
reproduced here in excerpt only, with the source file and page cited on every
answer, under the reproduction terms published on the originating sites.

Caliper is an independent student project. It is not affiliated with, endorsed
by, or connected to any government department, and it is not an official
source. The documents linked above, and the portals that publish them, are the
only authority for any decision about eligibility, amounts or deadlines. Verify
anything that matters before acting on it.