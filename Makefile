.PHONY: install test eval eval-compare run demo ui ui-install up down ingest loadtest clean

install:
	pip install -r requirements.txt

test:
	OFFLINE=1 python -m pytest tests/ -q

eval:
	python eval/run_eval.py

eval-compare:
	python eval/run_eval.py --compare

run:
	uvicorn app.main:app --reload --port 8000

demo:
	python scripts/dev_offline.py

ui-install:
	cd frontend && npm install

ui:
	cd frontend && npm run dev

up:
	docker compose up --build -d

down:
	docker compose down

ingest:
	python -m app.ingest docs/

loadtest:
	python scripts/loadtest.py --concurrency 8 --requests 40

clean:
	rm -rf __pycache__ .pytest_cache traces/*.jsonl eval/results.json
