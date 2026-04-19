# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Flask application that tracks LLM usage from locally-run Ollama models. Acts as an Ollama proxy (port 8080) that intercepts, logs, and analyzes every LLM call. Provides a web dashboard for usage metrics, on-premise vs. cloud cost comparison, and LLM-as-judge quality evaluation.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database and run migrations
flask db init
flask db migrate -m "initial"
flask db upgrade

# Seed cloud pricing data (run once after db upgrade)
python scripts/seed_cloud_pricing.py

# Run the app (proxy on port 8080)
python wsgi.py
# or
flask run --port 8080

# Run tests
pytest tests/

# Run a single test file
pytest tests/test_cost_calculator.py -v

# Run a single test
pytest tests/test_api.py::test_submit_feedback -v
```

## Integration with Ollama apps

**Option 1 — Proxy (recommended):** Change your LangChain/LlamaIndex Ollama base URL from `http://localhost:11434` to `http://localhost:8080/proxy`. Zero other changes needed.

**Option 2 — Callback:** Attach `LLMUsageCallbackHandler` to your LangChain LLM:
```python
from app.integrations.langchain_callback import LLMUsageCallbackHandler
handler = LLMUsageCallbackHandler(tracker_url="http://localhost:8080", source_app="my-app")
llm = Ollama(model="llama3", callbacks=[handler])
```

## Architecture

```
app/
├── __init__.py          # create_app() factory; registers blueprints, starts background evaluator
├── config.py            # BaseConfig / DevelopmentConfig / ProductionConfig / TestingConfig
├── extensions.py        # db, migrate singletons
├── models/              # SQLAlchemy models: LLMRequest, UserFeedback, LLMEvaluation, CloudPricing, OnPremConfig
├── proxy/               # Ollama proxy blueprint at /proxy — intercepts /api/generate and /api/chat
│   └── middleware.py    # forward_request(): streaming + buffered, logs to LLMRequest table
├── api/                 # Analytics REST API at /api/v1
│   └── routes.py        # Endpoints: /requests, /stats/summary, /stats/timeseries, /models, /feedback, /evaluate, /costs/comparison, /ingest
├── dashboard/           # Server-rendered HTML pages at /
│   └── routes.py        # index, models, requests, costs, evaluations
├── services/
│   ├── ollama_client.py    # Calls real Ollama directly (used by judge to avoid recursive logging)
│   ├── cost_calculator.py  # On-prem vs cloud cost math
│   ├── judge_service.py    # LLM-as-judge evaluation; background daemon thread
│   └── stats_service.py    # Aggregate DB queries for dashboard and API
└── integrations/
    └── langchain_callback.py  # LangChain BaseCallbackHandler alternative integration
```

## Key design decisions

- **Proxy port 8080, Ollama port 11434**: The proxy forwards all Ollama paths transparently. Only `/api/generate` and `/api/chat` are intercepted for logging; all others pass through unchanged.
- **Streaming**: The proxy uses `stream_with_context` to forward NDJSON chunks to the client in real time while accumulating token counts and timing. The final Ollama chunk contains `prompt_eval_count` and `eval_count` — these are the authoritative token counts.
- **Judge calls bypass the proxy**: `ollama_client.py` calls Ollama's native port directly to avoid judge invocations inflating usage metrics.
- **Background evaluator**: Started in `create_app()` only when `JUDGE_AUTO_EVALUATE=true`. Daemon thread, so it exits when the process exits. Replace with Celery if needed.
- **SQLite → PostgreSQL**: Only `DATABASE_URL` needs to change. All queries use SQLAlchemy ORM; migrations via Flask-Migrate/Alembic are DB-agnostic.
- **Cloud cost comparison**: `CloudPricing` table stores $/1K token rates. The comparison is always hypothetical — what the same token volume would have cost on cloud. Seed with `scripts/seed_cloud_pricing.py`, add providers by inserting rows.

## Data flow

```
Client app → POST /proxy/api/chat
  → middleware.py intercepts, records start time
  → forwards to http://localhost:11434/api/chat
  → streams response back to client
  → on completion: extracts token counts, computes latency/TPS
  → saves LLMRequest row to DB
  → (background) judge_service evaluates and saves LLMEvaluation
```

## Environment variables

All config via `.env` (copy `.env.example`). Key vars:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | SQLite dev.db | SQLAlchemy connection string |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Real Ollama address |
| `JUDGE_MODEL` | (empty = same model) | Model used for quality evaluation |
| `JUDGE_AUTO_EVALUATE` | `true` | Enable background evaluation sweep |
| `HARDWARE_COST_USD` | `2000` | On-prem hardware purchase price |
| `ELECTRICITY_COST_KWH` | `0.12` | USD per kWh |
