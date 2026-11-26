<div align="center">

# 📐 Caliper

### An Evidence Gated Document Agent

Ingest → Retrieve → Grade → Answer → **Verify** → Release or Refuse

![status](https://img.shields.io/badge/status-running-3FB950)
![live](https://img.shields.io/badge/live-caliper--rag.vercel.app-000000?logo=vercel&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-state%20graphs-1C3C3C?logo=langchain&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-API-8E75B2?logo=googlegemini&logoColor=white)
![Qdrant](https://img.shields.io/badge/Qdrant-vectors-DC244C?logo=qdrant&logoColor=white)
![React](https://img.shields.io/badge/React-Vite-61DAFB?logo=react&logoColor=black)
![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)
![tests](https://img.shields.io/badge/tests-69%20passing-3FB950)
![offline](https://img.shields.io/badge/runs%20offline-no%20API%20key-5EEAD4)

**Answers only what the documents support. Cites every claim. Refuses the rest.**

🌐 **[Try it live](https://caliper-rag.vercel.app)** · 🎬 [Demo video](media/caliper-demo.mp4) · 📊 [Slides](media/caliper-deck.pdf) · 📘 [Documentation](DOCUMENTATION.md)

*A caliper measures precisely. This one measures whether its own answers are actually supported by the documents it read.*

</div>

---

## 🌐 Live

**[caliper-rag.vercel.app](https://caliper-rag.vercel.app)**

Running against the real corpus described in [`SOURCES.md`](SOURCES.md): six Indian government scholarship documents, 170 pages, 289 chunks, in a hosted Qdrant cluster. Ask it something a scheme document answers and it answers with the page cited. Ask it something they do not cover and it refuses.

Two honest notes about the hosted copy.

It runs on serverless functions, so the rolling latency window at `/metrics` and the per request trace files are not meaningful there. Those are features of the service run as a service. Use `docker compose up` to see them.

It answers from a free model quota, so the demo caps itself at a number of questions per hour and says so plainly when it hits the cap. That window is per running instance rather than global, which makes it a speed bump against casual abuse and not a quota system. Run your own copy if you want to hammer it.

---

## 🎬 Demo

![Caliper answering, then refusing](media/caliper-demo.gif)

An answer released with its citation, then a draft withheld because the sources did not support it.

| | |
|---|---|
| 🌐 **Live service** | [caliper-rag.vercel.app](https://caliper-rag.vercel.app) · the real corpus, real answers, real refusals |
| 🎥 **Full walkthrough, 64 seconds** | [`media/caliper-demo.mp4`](media/caliper-demo.mp4) · one answer and all three refusal paths, with the agent trace and the cost panel |
| 📊 **Presentation, 13 slides** | [`media/caliper-deck.pdf`](media/caliper-deck.pdf) · architecture, the three refusal paths, the evaluation design and references |
| 📘 **Full documentation** | [`DOCUMENTATION.md`](DOCUMENTATION.md) · every module, every command, verified by running it |

Both recordings used the deterministic offline stub, so the answer *text* in them is a placeholder. What they show is the decision path and the refusal gates, not answer quality. For real answers use the live link; for measured answer quality see [Results](#-results).

---

## 🎯 Why refusal is the feature

A demo that answers everything is easy. The hard part, and the part that matters when the subject is who qualifies for a ₹6,000 benefit, is knowing when the retrieved text does **not** settle the question.

So the agent has two reflection points and is measured on the questions it should decline:

| Reflection point | What it decides |
|---|---|
| **grade / plan** | Before answering, whether what it gathered is genuinely relevant. Topical overlap is not relevance. |
| **verify** | After drafting, whether every claim is supported by the source text. An unsupported draft is withheld, not returned. |

The eval harness runs the whole question set twice, verification off then on, and reports the difference. That number is in this README, and it did not point the way I hoped.

---

## 🧠 Two reasoning modes, same corpus

The point is the comparison. Both are tested, and both run in the eval harness.

**Agent mode.** The model is shown a toolbox and decides, each turn, what to call and with what arguments. It sees the result and decides again.

```
question → ┌─ plan ──→ act ──→ observe ─┐ → answer → verify → ✓ / refuse
           └────── loop, max 5 steps ───┘
```

**Pipeline mode.** A fixed path with no tool choice.

```
route → retrieve → grade ─┬─ generate → verify → ✓ / refuse
                          ├─ rewrite (≤2) ↺
                          └─ no evidence → refuse
```

### 🧰 The toolbox

| Tool | What it does |
|---|---|
| `search_documents(query)` | hybrid dense and BM25 retrieval over the corpus |
| `lookup_number(query)` | the same retrieval, re ranked toward passages containing figures |
| `calculate(expression)` | arithmetic parsed from an AST, never `eval()` |
| `current_date()` | today, for deadline and window questions |
| `finish(reason)` | stop gathering: enough evidence, or clearly none |

A failing tool returns `{"ok": false, "error": ...}` rather than raising, so one bad call degrades that step and the agent can choose differently next turn.

**The step budget is not decoration.** An unbounded agent loop with a paid model behind it is a bill, and `test_loop_is_bounded_by_max_steps` proves a runaway planner stops at `MAX_STEPS`.

### 🔍 Why hybrid retrieval

Scheme documents are full of exact tokens a dense embedding blurs: `SC/ST`, `₹6,000`, `2 hectares`, `Section 4(2)`. Dense search alone misses those, BM25 alone misses paraphrase. Reciprocal Rank Fusion combines them by **rank position**, not score, because a cosine similarity of 0.82 and a BM25 score of 14.3 are not on comparable scales. Averaging them is meaningless.

---

## 🖥️ The interface

React with Vite and Tailwind, streaming over server sent events.

- **The agent's reasoning, live.** Each tool call appears as it happens: what it chose, its stated reason, the arguments, how long it took, what came back. Not a spinner.
- **Citations as chips.** `[S1]` markers in the answer are clickable and tied to the source list.
- **A cost panel on every answer.** Latency, tokens in and out, model calls, tool calls, and cost per request.
- **Refusals that look deliberate**, not broken.
- **An evaluation view** with live service metrics and p95 latency per graph node.

`POST /ask/stream` is server sent events. `EventSource` only does GET and the question belongs in a POST body, so the frontend parses SSE frames off the fetch body stream by hand.

---

## 💰 Cost is `null` on purpose

`cost_usd` stays `null` until you fill `config/pricing.yaml` and set `verified: true` with the date you read the official pricing page.

Published token prices change. A cost figure whose provenance nobody recorded is worse than an honest "unconfigured", so the code refuses to invent one. The UI explains this where the number would be.

**This is not hypothetical.** The model these results were measured on, `gemini-3.5-flash-lite`, is available through the API but is not listed on Google's published pricing page. There is no verified rate to record, so Caliper reports no cost rather than a number it made up. This is the case that behaviour was written for, and it caught it.

---

## 📊 Results

28 questions, a hand written answer key, six Indian government scholarship documents totalling 170 pages ingested as 289 chunks. Model `gemini-3.5-flash-lite`. Every figure below comes from [`eval/results.json`](eval/results.json), which is committed, and reproduces with `make eval-compare`.

| Metric | verify OFF | verify ON |
|---|---|---|
| Answer accuracy (answerable) | **0.87** | **0.87** |
| Refusal accuracy (unanswerable) | **1.00** | **1.00** |
| Routing accuracy (out of scope) | **1.00** | **1.00** |
| **Hallucination rate** | **0.00** | **0.00** |
| Latency p50 | 6.8s | 9.0s |
| Input tokens, whole run | 64,115 | 83,759 |
| Cost per question | unconfigured | unconfigured |

Thirteen of fifteen answerable questions answered correctly with the expected document cited. All eight unanswerable and all five out of scope questions were refused correctly, in both runs.

Corpus: *6 documents, 289 chunks, ingested 2026-11-26.*
Evaluation set: *28 questions: 15 answerable / 8 unanswerable / 5 out of scope.*

Latency p95 is deliberately not quoted. The run was made on a free tier that answers 429 with a stated retry delay, and those sleeps fall inside the timed section, so the tail measures someone else's rate limiter rather than this system.

**Agent against pipeline was not measured in this run.** The comparison harness exists and both modes run on the same corpus, but the figures above are the verify ablation only. Publishing a mode comparison without having run it would be the exact failure this project is about.

### Cost of a refusal against an answer

Refusal paths are ordered cheapest first, and the ordering is worth what it costs:

| Path | Model calls | Input tokens | Latency |
|---|---|---|---|
| Out of scope, refused at the router | 1 | 112 | 1.6s |
| In scope, no evidence, refused after gathering | 1 | 383 | 3.0s |
| Grounded answer with citations | 4 | 5,006 | 12.9s |

An out of scope question is rejected for one forty fifth of the input tokens of an answer, and never touches the vector store. That is the whole reason routing happens before retrieving.

### The verify node did not earn its tokens on this corpus

| | verify OFF | verify ON |
|---|---|---|
| Hallucination rate | 0.00 | 0.00 |
| Input tokens | 64,115 | 83,759 |

It caught nothing and cost 19,644 extra input tokens, about 31 percent more. Published rather than buried. The honest reading is that the two refusal paths ahead of it already removed everything it would have caught here, not that self verification is worthless. A corpus with closer near misses would be a fairer test, and this one was not adversarial enough to make the node work for its tokens.

### What the evaluation caught

Running against a real corpus found a defect in the one feature this project exists to provide.

**Citations were silently dropping.** Answers shipped with markers like `[S1, S2, S3]` in the text and an empty sources list behind them, while the interface still said every claim had been checked. The parser tested for the literal string `[S1]`, which matches a single marker but not a grouped one. An answer that looks verified and is not is worse than an answer with no citations at all. Found by the eval reporting `cited nothing` on answers that were otherwise correct, reproduced by hand, and fixed in `_cited_markers`, which now reads marker numbers from inside bracketed groups so `[S1]`, `[S1, S2]` and `[S1][S2]` are all understood.

**Two questions in the answer key were wrong, not the system.** They were labelled unanswerable and scored as hallucinations. Reading what the system actually said showed it had cited real pages, answered accurately, and stated plainly what the excerpts did not cover. The corpus did support those answers. The labels were corrected against the documents. Relabelling because a document proves a label wrong is correct; relabelling because the number looks better is not, and the difference is the entire value of an evaluation.

### ⚠️ Known limitations

Measured, not guessed. Every item below was observed during evaluation on this corpus.

**The router over refuses some in scope questions.** "Can a student change an application after final submission" was refused as out of scope in both runs, although the user manual answers it directly. Procedural questions about the portal read as off topic.

**Routing is not deterministic.** One question failed with verify off and passed with verify on while another did the reverse, both at the router, which runs before the verify node. A single run of a single question is not a result.

**Cross document confusion is real in this corpus.** Two of the six documents describe a scheme called Top Class Education with an eight lakh income ceiling, written as `Rs. 8.00 lakh` in one and `Rs.8,00,000` in the other. Asked about the Scheduled Caste scheme, the system sometimes answers from the disability scheme document. The figure happens to match, so the answer is correct by accident. Had the ceilings differed it would have been confidently wrong with a plausible citation.

**Retrieval reads have no retry.** Writes during ingestion back off and retry; a dropped connection during a query surfaces to the user as an error.

**The evaluation matcher is a substring check.** A correct answer written in a different number format scores as a failure, so the answer key uses the notation each document uses.

**The public demo cap is per instance, not global.** On serverless a burst spread across instances can exceed the nominal rate. It is a speed bump, not a quota system.

**BM25 is built in process** by scanning the collection at startup. Fine at a few thousand chunks, replace with Qdrant sparse vectors before it is not.

**Scanned PDFs with no text layer ingest as nothing.** One page of the 170 in this corpus has no text layer, and `app.ingest` reports the count rather than passing it through silently. Run OCR on anything worse.

**No recall@k against a labelled relevance set.** Retrieval is measured end to end only.

**Single turn.** No conversation memory.

**The question set and the router prompt are specific to this corpus.** Point the pipeline at different documents and both must be rewritten, or the numbers mean nothing.

---

## 🚀 Running it

### See the UI in two minutes, with no API key, no network and no Qdrant

```bash
pip install -r requirements.txt
python scripts/dev_offline.py          # API on :8000, stub model, fictional corpus

cd frontend && npm install && npm run dev   # UI on :5173
```

A deterministic stub stands in for the model. Nothing it answers means anything, the schemes are invented, but every endpoint, the streaming trace and the whole UI work end to end on a fresh clone.

```bash
make test        # 69 tests, fully offline
```

### For real

```bash
cp .env.example .env          # add your GEMINI_API_KEY
docker compose up -d qdrant   # vector store on :6333

# put scheme PDFs in docs/ — see SOURCES.md
python -m app.ingest docs/ --dry-run   # check chunking and scanned-page count
python -m app.ingest docs/

make run                      # API  → http://localhost:8000/docs
cd frontend && npm run dev    # UI   → http://localhost:5173
```

Then write `eval/questions.yaml` from your own documents, copying `eval/questions.example.yaml`, and run:

```bash
make eval-compare
make loadtest
```

### Deploying

The live service runs on Vercel as a single project: the React build is served as static files, and `api/index.py` exposes the FastAPI app as a serverless function. `vercel.json` holds the build command and the rewrite that maps `/api/*` onto it, so deployed paths match what Vite proxies in development and the app itself stays unaware of where it is running.

Import the repository in Vercel, set the application preset to **Other** so `vercel.json` is respected, and set five environment variables:

```
GEMINI_API_KEY      your key, on a project with no billing account attached
QDRANT_URL          your hosted cluster endpoint, including :6333
QDRANT_API_KEY      your cluster key
GEN_MODEL           gemini-3.5-flash-lite
OFFLINE             0
```

`ALLOWED_ORIGINS` and `MAX_ASKS_PER_HOUR` are optional and default sensibly.

Serverless suits the request path and not the observability: the rolling metrics window and the JSONL traces assume one long lived process, so they are not meaningful on the hosted copy. The repository also ships a `Dockerfile` and `docker-compose.yml` for running it as an actual service, where they are.

```bash
docker compose up --build -d
```

The container reads `$PORT`, runs as a non root user, and ships no secrets.

---

## 🗂️ Layout

```
api/
  index.py          Vercel entrypoint; strips the /api prefix in ASGI
app/
  config.py         settings; pricing loaded from YAML, never hardcoded
  llm.py            Gemini client, offline stub, retry, token and cost metering
  tools.py          the agent's toolbox + an AST-parsed calculator
  store.py          chunking, Qdrant dense search, BM25, RRF fusion
  ingest.py         PDF/text → chunks → embeddings, reports empty pages
  observability.py  rolling metrics window + JSONL request traces
  graph/
    nodes.py        route, retrieve, grade, rewrite, generate, verify
    agent.py        the plan → act → observe loop
    build.py        both graphs, with a verify-off ablation path
  main.py           /ask, /ask/stream (SSE), /metrics, /healthz, /documents
frontend/           React + Vite + Tailwind; live agent trace, citations, cost
eval/               question set, answer key, harness, ablation, results.json
tests/              69 offline tests
media/              demo video, preview GIF, slide deck
scripts/
  dev_offline.py    whole stack with no key and no Qdrant
  loadtest.py       concurrency test reporting p50/p95/p99 and errors
```

---

## ✍️ Writing the question set

The evaluation set is the project. Three kinds, and the second is the one most RAG demos skip:

| Kind | What it tests |
|---|---|
| **answerable** | The corpus settles it. Checked against required substrings and the expected citation source. |
| **unanswerable** | Plausible, on topic, genuinely not in the documents. The system must refuse. The share it answers anyway is the hallucination rate. |
| **out_of_scope** | Not about the corpus at all. Refused before any retrieval spend. |

Grading is substring and citation assertions against a human written key, not a model marking its own homework.

Two rules learned the hard way while writing [`eval/questions.yaml`](eval/questions.yaml). Take the required substring from the document, never from the system's own answer, or the eval stops measuring anything. And check that an unanswerable question really is absent before trusting the label, because one the corpus quietly answers will be scored as a hallucination that never happened.

---

## 📄 Disclaimer

**This is an independent engineering project. It is not affiliated with, endorsed by, or operated on behalf of any government department or agency.**

- Answers come from whatever documents were ingested, which may be outdated, incomplete or superseded. **Always verify eligibility, benefit amounts and deadlines on the scheme's official portal before acting.**
- Nothing here is legal, financial or benefits advice.
- This repository distributes **no government documents**. It ships the ingestion pipeline, and the operator downloads source documents themselves from official portals. See `SOURCES.md`.
- No government logo, emblem, seal or branding is used anywhere, and "Caliper" is not presented as an official service.
- No personal data is collected. The question text and timings are written to a local trace file so latency and cost can be measured. The service asks for no Aadhaar number, bank detail or other identifier, and you should not send one.
- Fetch source documents manually and respect each portal's terms of use. Do not bulk scrape.

---

## 📜 Licence

MIT. Applies to this source code only, not to any document you ingest.

<div align="center">

**Bollu Jnana Keerthana** · [jnanabollu@gmail.com](mailto:jnanabollu@gmail.com) · [github.com/Jnana1964](https://github.com/Jnana1964)

</div>
