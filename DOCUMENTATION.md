# Caliper

Complete project documentation.

A caliper measures precisely. This one measures whether its own answers are actually supported by the documents it read.

***

## 1. What this is

Caliper is a question answering service built on top of a document corpus. It does three things that an ordinary retrieval chatbot does not.

**It chooses its own tools.** The language model is shown a registry of tools and decides on every turn which one to call and with what arguments. It sees the result and decides again. That loop runs under a hard step budget.

**It verifies itself.** Before answering it grades whether the evidence it gathered is genuinely relevant. After drafting it checks every claim in the draft against the source text. If a claim is not supported, the answer is withheld rather than returned.

**It measures everything.** Tokens in and out, tokens per second, cost per request, latency per graph node and per tool call. All of it written to a replayable trace file and streamed live to the browser.

Stack: Python, FastAPI, LangGraph, Gemini, Qdrant, React, Vite, Tailwind, Docker.

***

## 2. The problem it solves

A naive retrieval system fails in four ways. Caliper addresses each one, and each fix produces a number you can measure.

**Retrieval misses the exact fact.** Embeddings capture meaning, so they blur precise tokens such as a rupee amount, a land limit or a section number. Ask for the land limit and a dense search happily returns a paragraph about land that does not contain the figure.

The fix is hybrid retrieval. Dense vectors for meaning, BM25 for exact terms, fused with Reciprocal Rank Fusion. RRF fuses by rank position rather than by score, because a cosine similarity of 0.82 and a BM25 score of 14.3 are not on comparable scales. Averaging them is meaningless.

**It answers anyway.** Give a language model weak context and it still produces fluent, confident, wrong text. Nothing in the output signals that it was unsupported.

The fix is two independent judges. The grade step asks whether the retrieved text is actually relevant before answering. The verify step checks the draft claim by claim against the retrieved text afterwards. Note what this is not: asking the model whether it is sure. Self reported confidence is badly calibrated and tells you nothing. The check has to be a separate call with the source text in front of it.

**One shallow pass on a compound question.** A question that contains three questions is served badly by one retrieval.

The fix is the agent loop. The model can search, then look up a figure, then calculate, then stop, in whatever order the question demands.

**Cost is invisible and unbounded.** Every call hits the model, a retry loop can spiral, and nobody knows what one answer costs.

The fix is metering on every request and a hard step budget on the loop. An unbounded agent loop with a paid model behind it is a cost incident waiting to happen.

***

## 3. Architecture

### Agent mode, the default

```
question
   |
   v
reason_act  (plan -> act -> observe, repeat, max MAX_STEPS)
   |
   v
answer      (draft with inline citations)
   |
   v
verify      (check every claim against sources)
   |
   +--> grounded      -> return answer and citations
   +--> not grounded  -> withhold, return refusal
```

On each turn of reason_act the model receives the question, the tool registry and everything gathered so far. It returns JSON naming one tool and its arguments. The tool runs, the observation is appended to a scratchpad, and the loop repeats until the model calls `finish` or the step budget is exhausted.

### Pipeline mode

```
route ----- out of scope -------------------------> refuse
  |
  v
retrieve -> grade -+- relevant found --> generate -> verify -> answer or refuse
                   |
                   +- nothing relevant, retries left --> rewrite --+
                   |                                               |
                   +- nothing relevant, retries spent --> refuse   |
                           ^                                       |
                           +---------------------------------------+
```

No tool selection happens here. The path is fixed.

**Why both exist.** Having two modes on the same corpus means the question "does letting the model choose actually help" can be answered with a measurement instead of an opinion. Both run in the evaluation harness.

***

## 4. The toolbox

Defined in `app/tools.py`. A tool is a name, a description the model reads, an argument schema, and a Python callable.

**search_documents(query)**
Hybrid dense and BM25 retrieval over the corpus. The default move for any factual question.

**lookup_number(query)**
The same retrieval, reranked so passages containing digits, percentages or currency come first. Eligibility answers usually turn on a figure, and dense embeddings blur figures.

**calculate(expression)**
Arithmetic only, parsed from an abstract syntax tree. Deliberately not `eval()`. The expression comes from a language model, which means it is untrusted input, and `eval()` on model output is a remote code execution hole with extra steps. There is a test that rejects `__import__('os').system('ls')`.

**current_date()**
Today's date, for questions that depend on whether a window or deadline is still open.

**finish(reason)**
Stop gathering. Called when there is enough evidence, or when the documents clearly cannot answer.

Every tool returns a dictionary with an `ok` flag. A tool that raises is caught and returned as a failure, so one bad call degrades that step instead of killing the request. The agent sees the failure and can choose differently on the next turn.

***

## 5. Project structure

```
caliper/
  app/
    config.py          settings, and pricing loaded from YAML rather than hardcoded
    llm.py             Gemini client, offline stub, token and cost metering
    tools.py           the agent toolbox and the safe calculator
    store.py           chunking, Qdrant dense search, BM25, RRF fusion
    ingest.py          PDF and text to chunks to embeddings
    observability.py   rolling metrics window and JSONL request traces
    models.py          pydantic request and response schemas
    main.py            FastAPI application and all endpoints
    graph/
      state.py         the shared state passed between nodes
      nodes.py         route, retrieve, grade, rewrite, generate, verify
      agent.py         the plan, act, observe loop
      build.py         both graphs, plus a verify off ablation path
  frontend/
    src/
      App.jsx          layout and streaming state
      lib/api.js       fetch helpers and the SSE frame parser
      components/      AgentTrace, AnswerCard, CostPanel, Sidebar, EvalPanel
  eval/
    questions.example.yaml   the question set format
    run_eval.py              the harness and the ablation runner
  tests/                     69 tests, all offline
  scripts/
    dev_offline.py     run the whole stack with no key and no Qdrant
    loadtest.py        concurrency test reporting p50, p95, p99 and errors
  config/pricing.yaml  token prices, filled in by a human
  docs/                your source documents go here
  Dockerfile
  docker-compose.yml
  Makefile
```

***

## 6. Prerequisites

* Python 3.11 or newer
* Node.js 18 or newer, for the interface
* Docker, for the vector database
* A Gemini API key, only when you want real answers

The offline mode below needs none of the last three.

***

## 7. Quick start, no API key and no network

This runs the entire stack against a deterministic stub model and a fictional two document corpus. Nothing it answers means anything. It exists so you can see the interface and prove the plumbing works on a fresh clone.

```bash
cd caliper
pip install -r requirements.txt

python scripts/dev_offline.py
```

The API is now on `http://localhost:8000`. In a second terminal:

```bash
cd caliper/frontend
npm install
npm run dev
```

The interface is now on `http://localhost:5173`. Ask a question and watch the agent trace fill in.

Run the test suite:

```bash
cd caliper
OFFLINE=1 python -m pytest tests/ -q
```

Expected output: `69 passed`.

***

## 8. Full setup, real documents and a real model

### Step one, configuration

```bash
cp .env.example .env
```

Open `.env` and set `GEMINI_API_KEY`. Leave the rest at defaults for now.

### Step two, start the vector database

```bash
docker compose up -d qdrant
```

Confirm it is up at `http://localhost:6333/dashboard`.

### Step three, add documents

Put PDF, text or markdown files into `docs/`. See `SOURCES.md` for where to get Indian government scheme documents and why this repository ships none of them.

Always dry run first:

```bash
python -m app.ingest docs/ --dry-run
```

Read the line that says `pages no text`. Many government PDFs are scans with no text layer, and a scan ingests as nothing. If that count is high, run OCR on those files before continuing:

```bash
ocrmypdf input.pdf output.pdf
```

Then ingest for real:

```bash
python -m app.ingest docs/
```

### Step four, run it

```bash
uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```bash
cd frontend
npm run dev
```

Interactive API documentation is at `http://localhost:8000/docs`.

***

## 9. Command reference

Every command below is run from the project root unless stated.

**Install Python dependencies**
`pip install -r requirements.txt`

**Run the test suite**
`OFFLINE=1 python -m pytest tests/ -q`

**Run one test file**
`OFFLINE=1 python -m pytest tests/test_agent.py -q`

**Run one test with full output**
`OFFLINE=1 python -m pytest tests/test_agent.py::TestAgentLoop::test_loop_is_bounded_by_max_steps -v`

**Offline demo, no key and no Qdrant**
`python scripts/dev_offline.py`

**API against real documents**
`uvicorn app.main:app --reload --port 8000`

**Chunk and inspect without embedding**
`python -m app.ingest docs/ --dry-run`

**Ingest into the vector store**
`python -m app.ingest docs/`

**Evaluation, verify on only**
`python eval/run_eval.py`

**Evaluation, verify off only**
`python eval/run_eval.py --no-verify`

**Evaluation, both and print the difference**
`python eval/run_eval.py --compare`

**Load test a running service**
`python scripts/loadtest.py --url http://localhost:8000 --concurrency 8 --requests 40`

**Start Qdrant only**
`docker compose up -d qdrant`

**Start everything in Docker**
`docker compose up --build -d`

**Stop everything**
`docker compose down`

**Frontend, install once**
`cd frontend && npm install`

**Frontend, development server**
`cd frontend && npm run dev`

**Frontend, production build**
`cd frontend && npm run build`

### Makefile shortcuts

`make install`, `make test`, `make demo`, `make run`, `make ingest`, `make eval`, `make eval-compare`, `make loadtest`, `make ui-install`, `make ui`, `make up`, `make down`, `make clean`

***

## 10. API reference

**GET /healthz**
Service state. Reports whether anything is indexed, how many chunks, which model, whether offline mode is on, whether pricing is verified, and any startup error.

**GET /metrics**
Rolling window over recent requests. Latency p50, p95 and p99, output tokens per second, cost per request, refusal rate, outcome counts, and p95 latency broken down per graph node.

**GET /documents**
What the agent can actually see. An empty list here explains every refusal.

**POST /ask**
Body: `{"question": "...", "mode": "agent" | "linear", "trace": true | false}`

Returns the outcome, the answer, citations, whether it was grounded, counts of retrieved and relevant passages, latency, full usage with cost, the agent steps and the tools used.

Example:

```bash
curl -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the benefit amount?","mode":"agent","trace":true}'
```

**POST /ask/stream**
Same body. Returns server sent events. One `start` event, one `node` event per graph node, one `step` event per tool call, one `draft` event when the answer is written, and one `done` event carrying the same payload as `/ask`. An `error` event is emitted instead of leaving the stream hanging.

The browser cannot use `EventSource` here because that only does GET and the question belongs in a POST body. The frontend therefore parses SSE frames off the fetch body stream by hand, in `frontend/src/lib/api.js`.

***

## 11. Configuration reference

All of these live in `.env`.

* **GEMINI_API_KEY** your key. Required unless OFFLINE is 1.
* **GEN_MODEL** generation model name. Default `gemini-2.5-flash`.
* **EMBED_MODEL** embedding model name. Default `gemini-embedding-001`.
* **EMBED_DIM** embedding dimensions. Default 768. Must match the Qdrant collection.
* **QDRANT_URL** default `http://localhost:6333`.
* **QDRANT_API_KEY** blank for local, required for Qdrant Cloud.
* **COLLECTION** collection name. Default `schemes`.
* **TOP_K** passages returned per search. Default 8.
* **RRF_K** the damping constant in Reciprocal Rank Fusion. Default 60. Higher values flatten the difference between ranks.
* **MAX_REWRITES** query rewrite attempts in pipeline mode. Default 2.
* **MAX_STEPS** hard ceiling on tool calls per question in agent mode. Default 5.
* **OFFLINE** set to 1 to use the deterministic stub. No network, no key, no cost.
* **TRACE_PATH** where request traces are written. Default `traces/trace.jsonl`.

### Pricing

`config/pricing.yaml` holds token prices in US dollars per million tokens.

These are not hardcoded in the application on purpose. Published API prices change, and a cost figure whose provenance nobody recorded is worse than no cost figure at all. Until `verified` is set to true, every response reports `cost_usd: null` and the metrics endpoint reports cost as unconfigured.

To enable cost reporting, read the official pricing page, fill in the rates, set `verified: true` and record the date you checked in `verified_on`.

***

## 12. Evaluation

This is the part that makes the project worth something. Everything else is scaffolding.

### Writing the question set

Copy `eval/questions.example.yaml` to `eval/questions.yaml` and replace every entry with questions written from your own documents.

Three kinds, and the second is the one most retrieval demos skip.

**answerable**
The corpus settles it. Checked against required substrings and the expected citation source. Write about fifteen.

**unanswerable**
Plausible, on topic, and genuinely not in the documents. The system must refuse. The share it answers anyway is the hallucination rate. Write about ten. These are the highest value entries in the whole project, because they are what reveals whether the system guesses.

**out_of_scope**
Not about the corpus at all. Must be refused at the router before any retrieval spend. Write about five.

Grading is substring and citation assertions against a key you wrote by hand. No model marks its own homework.

### Running it

```bash
python eval/run_eval.py --compare
```

This runs the whole set twice, once with the verify node disabled and once enabled, and prints the difference in hallucination rate. Results are written to `eval/results.json`.

Paste the real output into the README. Leave the table blank rather than filling it with numbers you have not measured. An unfilled table costs you nothing. An invented one costs you the interview.

### A warning about offline evaluation

Running the harness with `OFFLINE=1` will report that everything failed. That is correct and expected. The stub answers every question with fixed text, grades every chunk relevant and always votes grounded, so every check fails by construction. The harness prints a loud banner saying so. Offline evaluation proves the harness runs. It measures nothing about answer quality.

***

## 13. Testing

69 tests, all offline, no credentials needed.

`tests/test_units.py` covers chunking behaviour and overlap, deterministic chunk identifiers, tokenisation, the RRF formula, pricing arithmetic, percentile calculation and the offline stub.

`tests/test_graph.py` covers all four pipeline outcomes, the bounded rewrite loop, per node timing attribution, token accounting, retrieval ranking and every API endpoint.

`tests/test_agent.py` covers the safe calculator including rejection of function calls and names, every tool, unknown tool handling, missing argument handling, the agent loop and its step ceiling, the verify gate, the ablation path and the streaming endpoint.

Two tests are worth knowing by name because they prove design decisions rather than behaviour.

`test_rejects_function_calls` proves untrusted model output cannot execute code.

`test_loop_is_bounded_by_max_steps` builds a deliberately runaway planner that never calls finish, and proves it is stopped at the ceiling.

***

## 14. Deployment

### Cloud Run

```bash
gcloud run deploy caliper \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-env-vars "QDRANT_URL=<your qdrant url>,GEN_MODEL=gemini-2.5-flash" \
  --set-secrets "GEMINI_API_KEY=gemini-key:latest"
```

The container reads `$PORT`, runs as a non root user with uid 10001, and ships no secrets.

### The vector store in production

Qdrant Cloud has a free tier sufficient for this corpus size. Set `QDRANT_URL` and `QDRANT_API_KEY` accordingly.

### Before deploying anywhere real

CORS is currently wide open for local development. Narrow `allow_origins` in `app/main.py` first.

***

## 15. Known limitations

State these before anyone asks. Naming your own system's weaknesses is worth more than pretending it has none.

**BM25 is built in process at startup** by scanning the whole collection. Fine at a few thousand chunks. The first thing to replace if the corpus grows: move to Qdrant sparse vectors or an external search index.

**Verification costs an extra model call per request.** Whether that is worth paying is exactly what the ablation measures.

**Scanned PDFs with no text layer ingest as nothing.** The ingester reports the count of empty pages. OCR those first.

**Retrieval is measured end to end only.** There is no recall at k against a labelled relevance set.

**Single turn.** No conversation memory.

**No hierarchical delegation.** The agent is a single planner with a flat toolbox. Multiple cooperating agents are not implemented.

**Last write wins on conflicting state.** Not relevant here, but worth knowing the system makes no attempt at concurrency control over the vector store.

***

## 16. Troubleshooting

**`/ask` returns 503 saying no documents indexed**
Nothing is in the vector store. Run `python -m app.ingest docs/`. Check `GET /documents` to confirm.

**Ingest reports a high `pages no text` count**
Those PDFs are scans. Run OCR before ingesting or they contribute nothing.

**`GEMINI_API_KEY is not set`**
Either fill it in `.env` or run with `OFFLINE=1`.

**Qdrant connection refused**
`docker compose up -d qdrant`, then check `http://localhost:6333/dashboard`.

**Vector dimension mismatch on upsert**
`EMBED_DIM` changed after the collection was created. Delete the collection in the Qdrant dashboard and ingest again.

**The interface shows no data**
The API must be running on port 8000. The Vite dev server proxies `/api` to it. Check `http://localhost:8000/healthz` directly.

**Evaluation reports everything failed**
Check whether `OFFLINE` is set to 1. See section 12.

**Cost always shows unconfigured**
Expected until `config/pricing.yaml` has `verified: true`. See section 11.

***

## 17. Questions you will be asked

If you cannot answer these, do not put this project on your resume.

**Why hybrid retrieval instead of just embeddings?**
Dense vectors blur exact tokens such as amounts, limits and section numbers. An eligibility answer usually turns on exactly those. BM25 catches them. Dense catches paraphrase. Neither alone is enough.

**Why Reciprocal Rank Fusion instead of averaging the two scores?**
Because a cosine similarity and a BM25 score are not on comparable scales, so averaging them is arithmetic on incompatible units. RRF uses rank position, which is comparable by construction.

**How do you know the verify step helps?**
I measure it. The harness runs the same question set with the step disabled and enabled, and reports the difference in hallucination rate on the questions the documents cannot answer.

**Why not just ask the model whether it is confident?**
Self reported confidence is poorly calibrated. The verification is a separate call that is shown the draft and the source text and asked to check claim by claim. That is a different question from asking the model how it feels about its own output.

**What stops the agent looping forever?**
A hard step ceiling, `MAX_STEPS`. There is a test that constructs a planner which never calls finish and proves it is stopped. LangGraph will happily run a cycle forever. The meaningful bound is domain logic, not framework behaviour.

**Why parse the calculator expression instead of calling eval?**
The expression comes from a language model, which makes it untrusted input. `eval()` on untrusted input is remote code execution. The AST walker allows numeric literals and arithmetic operators and nothing else.

**What happens when a tool fails?**
It returns a failure result rather than raising. The agent sees the failure in its scratchpad and can choose a different tool on the next turn. One bad call degrades a step, not the request.

**Why is cost null?**
Because the prices have not been verified against the official page. Reporting a number whose provenance nobody recorded is worse than reporting nothing. Fill in the config and it starts reporting.

**What would you do next?**
Multiple cooperating agents with a planner that decomposes a compound question, confidence gated routing so a cheap model handles easy questions and an expensive one handles hard ones, and a semantic cache. Each of those is a measurable number, which is the point.

***

## 18. Disclaimer

This is an independent engineering project. It is not affiliated with, endorsed by, or operated on behalf of any government department or agency.

Answers come from whatever documents were ingested, which may be outdated, incomplete or superseded. Always verify eligibility, benefit amounts and deadlines on the scheme's official portal before acting.

Nothing produced by this software is legal, financial or benefits advice.

This repository distributes no government documents. It ships the ingestion pipeline. The operator downloads source documents themselves from official portals.

No personal data is collected. Question text and timings are written to a local trace file so that latency and cost can be measured. The service asks for no identity number, bank detail or other identifier, and none should be sent to it.

Licence: MIT, applying to this source code only and not to any document you ingest.
