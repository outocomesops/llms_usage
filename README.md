# LLM Usage Tracker

A Flask application that tracks, logs, and analyzes every LLM call made to locally-run Ollama models.

## What It Does

Local Ollama usage is a black box — you run models, they answer, but nothing tells you how many tokens were used, how fast responses came, or what it would have cost on a cloud provider. This tracker closes that gap.

The app acts as a transparent HTTP proxy sitting between your LangChain/LlamaIndex/curl clients and Ollama. Every `/api/generate` and `/api/chat` request is intercepted, logged to a SQLite database, and surfaced through a web dashboard — with no changes required to your prompts or model configuration, just a one-URL redirect.

The dashboard provides usage metrics, per-model performance comparisons, an on-premise vs. cloud cost breakdown (OpenAI, Anthropic, Google), and an optional LLM-as-judge quality evaluation that scores responses automatically in the background.

## Key Features

- **Transparent proxy** — redirect one URL and every Ollama call is captured, including streaming responses
- **LangChain callback** — alternative zero-proxy integration for LangChain apps
- **Live Ollama status** — dashboard panel showing which models are loaded in VRAM right now (polls `/api/ps` every 3s, no proxy traffic required)
- **Usage dashboard** — requests per day, tokens by model, source-app breakdown (Chart.js)
- **Cost comparison** — hypothetical cloud cost for the same token volume across 7+ cloud models
- **LLM-as-judge** — background evaluator scores coherence, relevance, and overall quality (1–5)
- **Inline feedback** — thumbs-up/down rating widget on every request detail page
- **REST API** — full JSON API at `/api/v1` for all metrics, feedback, and evaluation data
- **SQLite default, PostgreSQL-ready** — swap `DATABASE_URL` to migrate

## Architecture Overview

```
Client app → POST http://localhost:8080/proxy/api/chat
  → app/proxy/middleware.py   intercepts, records start time
  → forwards to http://localhost:11434/api/chat (real Ollama)
  → streams NDJSON back to client
  → on completion: saves LLMRequest row (tokens, latency, TPS)
  → background: judge_service evaluates and saves LLMEvaluation
```

Major modules:

| Path | Role |
|---|---|
| `app/__init__.py` | `create_app()` factory; registers blueprints, starts background evaluator |
| `app/config.py` | Dev / Prod / Test config classes |
| `app/models/` | SQLAlchemy models: `LLMRequest`, `UserFeedback`, `LLMEvaluation`, `CloudPricing`, `OnPremConfig` |
| `app/proxy/middleware.py` | Core proxy: streaming + buffered forwarding, DB logging |
| `app/api/routes.py` | REST API at `/api/v1` — requests, stats, feedback, evaluate, costs, live status |
| `app/dashboard/routes.py` | Server-rendered pages: Overview, Models, Requests, Costs, Evaluations |
| `app/services/` | `ollama_client`, `cost_calculator`, `judge_service`, `stats_service` |
| `app/integrations/langchain_callback.py` | LangChain `BaseCallbackHandler` alternative |
| `scripts/seed_cloud_pricing.py` | Seeds `CloudPricing` table with OpenAI / Anthropic / Google rates |

## Getting Started

**Prerequisites:** Python 3.11+, [Ollama](https://ollama.com) running on `localhost:11434`.

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd llms_usage

# 2. Create and activate a virtual environment
python -m venv .env
# Windows
.env\Scripts\activate
# macOS/Linux
source .env/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and edit environment config
copy .env.example .env     # Windows
# cp .env.example .env     # macOS/Linux
# Edit .env if needed (defaults work for local Ollama)

# 5. Initialize the database
flask db upgrade

# 6. Seed cloud pricing (run once)
python scripts/seed_cloud_pricing.py

# 7. Start the tracker (proxy on port 8080)
python wsgi.py
```

Open http://localhost:8080 — you should see the dashboard with a Live Ollama Status panel.

## Usage

### Connecting your apps

**Option 1 — Proxy (recommended, zero code change):**

Change the Ollama base URL in your app from:
```
http://localhost:11434
```
to:
```
http://localhost:8080/proxy
```

Example with LangChain:
```python
from langchain_community.llms import Ollama
llm = Ollama(model="llama3", base_url="http://localhost:8080/proxy")
```

**Option 2 — LangChain callback:**
```python
from app.integrations.langchain_callback import LLMUsageCallbackHandler
handler = LLMUsageCallbackHandler(tracker_url="http://localhost:8080", source_app="my-app")
llm = Ollama(model="llama3", callbacks=[handler])
```

### Dashboard pages

| URL | What you see |
|---|---|
| `/` | Overview KPIs, daily requests chart, live Ollama status |
| `/models` | Per-model stats and token usage over time |
| `/requests` | Paginated request log with model and date filters |
| `/requests/<id>` | Full prompt/completion, feedback widget, evaluation scores |
| `/costs` | On-prem vs. cloud cost comparison |
| `/evaluations` | Quality score scatter plot and lowest-quality request list |

### REST API

Base URL: `http://localhost:8080/api/v1`

| Method | Path | Description |
|---|---|---|
| `GET` | `/requests` | Paginated request list |
| `GET` | `/requests/<id>` | Single request with feedback and evaluation |
| `GET` | `/stats/summary` | Aggregate KPIs |
| `GET` | `/stats/timeseries` | Per-day token and request counts |
| `GET` | `/models` | Ollama models merged with DB stats |
| `GET` | `/live` | Currently loaded Ollama models (from `/api/ps`) |
| `POST` | `/feedback` | Submit thumbs rating |
| `POST` | `/evaluate` | Trigger LLM-as-judge evaluation |
| `GET` | `/costs/comparison` | On-prem vs. cloud cost report |
| `POST` | `/ingest` | Internal: LangChain callback posts here |

## Project Structure

```
llms_usage/
├── app/
│   ├── __init__.py              # App factory
│   ├── config.py                # Environment configs
│   ├── extensions.py            # db, migrate singletons
│   ├── models/                  # SQLAlchemy models
│   ├── proxy/                   # Proxy blueprint (/proxy)
│   ├── api/                     # REST API blueprint (/api/v1)
│   ├── dashboard/               # HTML dashboard blueprint (/)
│   ├── services/                # Business logic
│   ├── integrations/            # LangChain callback
│   └── templates/               # Jinja2 templates
├── migrations/                  # Alembic migration files
├── scripts/
│   └── seed_cloud_pricing.py    # One-time cloud pricing seed
├── tests/                       # pytest test suite (17 tests)
├── wsgi.py                      # Entry point
├── requirements.txt
├── .env.example                 # Environment variable template
└── CLAUDE.md                    # AI assistant context
```

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///llms_usage_dev.db` | SQLAlchemy connection string |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server address |
| `PROXY_PORT` | `8080` | Port the tracker listens on |
| `JUDGE_MODEL` | (same as request model) | Model used for quality evaluation |
| `JUDGE_AUTO_EVALUATE` | `true` | Enable background evaluation sweep |
| `JUDGE_EVAL_INTERVAL_MIN` | `10` | Minutes between auto-evaluation sweeps |
| `HARDWARE_COST_USD` | `2000` | On-prem hardware purchase price |
| `AMORTIZATION_MONTHS` | `36` | Hardware cost amortization period |
| `POWER_DRAW_WATTS` | `150` | Machine power draw for electricity cost |
| `ELECTRICITY_COST_KWH` | `0.12` | USD per kWh |
| `MAX_STORED_PROMPT_LEN` | `4000` | Max characters stored per prompt |
| `MAX_STORED_COMPLETION_LEN` | `4000` | Max characters stored per completion |

## Output / Exports

All data is stored in SQLite (or PostgreSQL if `DATABASE_URL` is changed). Key tables:

- `llm_request` — one row per intercepted LLM call (model, tokens, latency, TPS, prompt, completion)
- `user_feedback` — thumbs ratings linked to requests
- `llm_evaluation` — judge scores (coherence, relevance, overall, 1–5) linked to requests
- `cloud_pricing` — provider/model pricing rates ($/1K tokens)

Data is queryable via the REST API or directly via any SQLite client.

## Known Limitations

- **Traffic must go through the proxy** — direct calls to `localhost:11434` are not captured; the live status panel shows loaded models but cannot log token counts without proxy routing
- No authentication on any endpoint — suitable for local use only; add Flask-Login before any network exposure
- LangChain callback token counts depend on Ollama returning `prompt_eval_count`/`eval_count`; some model/version combos may return `None`
- Dashboard date filter uses UTC; chart day boundaries may be off if the host machine is in a non-UTC timezone
- `psycopg2-binary` is not installed by default — Windows requires C build tools; install separately when switching to PostgreSQL

## License / Contact

For issues or feedback, open an issue in the repository.
