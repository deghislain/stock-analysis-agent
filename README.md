# Stock Analysis Agent

Beginner-friendly, agentic stock analysis. Enter a ticker symbol and receive
an interactive dashboard and a downloadable PDF report — powered by Yahoo
Finance, Groq LLM, and Chart.js.

> **Disclaimer:** This tool is for **informational purposes only**.
> It does **not** constitute financial advice.
> Always consult a qualified financial adviser and do your own research
> before making any investment decision.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start — Docker (3 commands)](#quick-start-docker-3-commands)
3. [Quick Start — Local (no Docker)](#quick-start-local-no-docker)
4. [Environment Variables](#environment-variables)
5. [Architecture](#architecture)
6. [Project Structure](#project-structure)
7. [Running the Tests](#running-the-tests)
8. [How to Add a New Data Source](#how-to-add-a-new-data-source)
9. [How to Add a New Analysis Module](#how-to-add-a-new-analysis-module)
10. [Rate Limiting (Public Deployments)](#rate-limiting-public-deployments)
11. [Ticker Symbol Format](#ticker-symbol-format)

---

## Prerequisites

| Tool | Minimum version | Notes |
|---|---|---|
| Docker | 24 | Required for the Docker quick start |
| Docker Compose | 2.20 | Bundled with Docker Desktop |
| Python | 3.10 | Required for local (non-Docker) run |
| Node.js | 18 | Required for local (non-Docker) run |
| npm | 9 | Required for local (non-Docker) run |

A free [Groq API key](https://console.groq.com) is **required** for
AI-generated report summaries. Registration takes under a minute; no credit
card needed.

---

## Quick Start — Docker (3 commands)

```bash
# 1. Copy the environment template and add your Groq API key
cp .env.example .env
#    Open .env and set:  GROQ_API_KEY=gsk_...

# 2. Build and start both services
docker compose up --build

# 3. Open the app
#    http://localhost:5173
```

| Service | URL |
|---|---|
| Frontend (React app) | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| Swagger / OpenAPI docs | http://localhost:8000/docs |

Generated PDFs are stored in a Docker-managed named volume (`pdf_reports`) and
persist across container restarts. To stop the stack:

```bash
docker compose down          # stop — PDF volume is preserved
docker compose down -v       # stop AND delete the PDF volume
```

---

## Quick Start — Local (no Docker)

```bash
# 1. Clone and enter the repo
git clone <repo-url> stock-analysis-agent
cd stock-analysis-agent

# 2. Configure environment
cp .env.example .env
#    Open .env and set GROQ_API_KEY=gsk_...

# 3. Backend
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 4. Frontend (new terminal, from project root)
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser. The Vite dev server proxies
all `/api/*` requests to `http://localhost:8000` automatically.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your values. All variables are
optional except `GROQ_API_KEY`.

| Variable | Default | Required | Description |
|---|---|---|---|
| `GROQ_API_KEY` | _(empty)_ | **Yes** | Groq API key for LLM summaries. Free at [console.groq.com](https://console.groq.com) |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | No | Groq model ID. Alternatives: `llama3-70b-8192`, `mixtral-8x7b-32768` |
| `FMP_API_KEY` | _(empty)_ | No | Financial Modeling Prep key for the fundamentals fallback. Free at [financialmodelingprep.com](https://financialmodelingprep.com/developer/docs). FMP is skipped when empty. |
| `DEBUG` | `false` | No | Verbose logging + detailed error responses. Never `true` in production. |
| `CORS_ORIGINS` | `["http://localhost:5173","http://localhost:3000"]` | No | JSON array of allowed frontend origins |
| `PDF_OUTPUT_DIR` | `/tmp/stock_reports` | No | Where PDFs are written. Overridden to `/app/pdf_reports` by Docker Compose. |
| `PDF_CLEANUP_INTERVAL_SECONDS` | `1800` | No | How often (s) the cleanup task runs |
| `PDF_MAX_AGE_SECONDS` | `3600` | No | PDFs older than this (s) are deleted |
| `DATA_CACHE_TTL_SECONDS` | `300` | No | In-memory data cache lifetime (s) |

---

## Architecture

```
                         ┌─────────────────────────────────────┐
                         │           User Browser              │
                         └───────────┬─────────────────────────┘
                                     │  http://localhost:5173
                                     ▼
                         ┌─────────────────────────────────────┐
                         │      nginx  (frontend container)    │
                         │   Serves React SPA static bundle    │
                         │   Proxies /api/* → backend:8000     │
                         └───────────┬─────────────────────────┘
                                     │  Docker network (stock-agent-net)
                                     ▼
                         ┌─────────────────────────────────────┐
                         │    FastAPI + uvicorn  (port 8000)   │
                         │                                     │
                         │  GET  /api/validate/{ticker}        │
                         │  POST /api/analyse                  │
                         │  GET  /api/report/{job_id}          │
                         │  GET  /api/report/{job_id}/pdf      │
                         │  GET  /health                       │
                         └───────────┬─────────────────────────┘
                                     │
                               Orchestrator
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
              ▼                      ▼                      ▼
        DataAgent             FundamentalAgent       TechnicalAgent
              │                      │                      │
   Yahoo Finance (primary)    P/E, EPS, P/B        SMA, EMA, RSI
   Stooq (fallback 1)         debt-to-equity       MACD, Bollinger
   FMP   (fallback 2)         margins, score       Bands, score
              │
              ▼
        ResearchAgent                          ReportAgent
        DuckDuckGo news                 Groq LLM → summaries
        sentiment score                 ReportLab → PDF file
```

### Scoring model

```
overall_score = fundamental_score × 0.40
              + technical_score   × 0.40
              + sentiment_score   × 0.20

≥ 60  →  Buy
40–59 →  Hold
< 40  →  Sell
```

### Data fallback policy

Data sources are tried in priority order. All are free to use:

| Priority | Source | Data provided | API key needed? |
|---|---|---|---|
| 1 (primary) | Yahoo Finance (`yfinance`) | Price history + fundamentals | No |
| 2 (fallback) | Stooq (`pandas-datareader`) | Price history only | No |
| 3 (fallback) | FMP free tier (`httpx`) | Fundamentals only | Free key recommended |

Alpha Vantage is explicitly excluded — its free tier requires key registration.

### Async job model

`POST /api/analyse` returns **immediately** with a `job_id`. The full analysis
pipeline runs as a FastAPI `BackgroundTask`. The frontend polls
`GET /api/report/{job_id}` every 2 seconds until `status` becomes `"complete"`,
then renders the dashboard. This avoids long-lived HTTP connections and keeps
the API responsive.

---

## Project Structure

```
stock-analysis-agent/
├── backend/
│   ├── app/
│   │   ├── agents/         # Orchestration layer
│   │   │   ├── data_agent.py           # Fetches data via source fallback chain
│   │   │   ├── fundamental_agent.py    # Runs fundamental analysis
│   │   │   ├── technical_agent.py      # Runs technical analysis
│   │   │   ├── research_agent.py       # Fetches news via DuckDuckGo
│   │   │   └── report_agent.py         # Calls Groq LLM; builds ReportPayload
│   │   ├── analysis/       # Pure calculation modules (no I/O)
│   │   │   ├── fundamental.py          # P/E, EPS, debt, margins
│   │   │   ├── technical.py            # SMA, EMA, RSI, MACD, Bollinger
│   │   │   └── sentiment.py            # News headline sentiment scoring
│   │   ├── api/routes/     # FastAPI route handlers
│   │   │   ├── analysis.py             # POST /analyse, GET /validate/{ticker}
│   │   │   └── report.py               # GET /report/{job_id}[/pdf]
│   │   ├── core/
│   │   │   ├── orchestrator.py         # Coordinates the full pipeline
│   │   │   ├── llm_client.py           # Groq API wrapper + fallback template
│   │   │   └── job_store.py            # In-memory job state tracker
│   │   ├── data/
│   │   │   ├── base_source.py          # AbstractDataSource + StockData
│   │   │   ├── yahoo_finance.py        # Primary data source
│   │   │   ├── stooq_source.py         # Fallback 1: price history
│   │   │   ├── fmp_source.py           # Fallback 2: fundamentals
│   │   │   └── source_registry.py      # Fallback chain orchestration
│   │   ├── report/
│   │   │   └── pdf_generator.py        # ReportLab PDF builder
│   │   ├── schemas/
│   │   │   ├── analysis.py             # Request/response Pydantic models
│   │   │   └── report.py               # ReportPayload + JobStatusResponse
│   │   ├── config.py                   # Pydantic Settings (all env vars)
│   │   ├── logger.py                   # Structured JSON logging
│   │   └── main.py                     # FastAPI entry point + lifespan
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/     # UI building blocks
│   │   ├── hooks/          # useAnalysis — TanStack Query polling hook
│   │   ├── pages/          # Home (ticker entry) + Report (dashboard)
│   │   ├── services/       # Axios API client (api.ts)
│   │   └── types/          # TypeScript interfaces matching backend schemas
│   ├── nginx.conf          # nginx config (SPA fallback + /api proxy)
│   └── Dockerfile          # Multi-stage: Node build → nginx serve
├── backend/Dockerfile      # Python 3.12 slim + uvicorn
├── docker-compose.yml      # Boots backend + frontend with health checks
├── .env.example            # Copy to .env and fill in GROQ_API_KEY
└── README.md
```

---

## Running the Tests

```bash
cd backend
source .venv/bin/activate   # or activate your environment

python -m pytest                                         # all tests
python -m pytest -v                                      # verbose output
python -m pytest --cov=app --cov-report=term-missing     # with coverage
```

---

## How to Add a New Data Source

The data layer uses a fallback chain defined in
`backend/app/data/source_registry.py`. Adding a new source takes three steps.

**1. Implement `AbstractDataSource`**

Create `backend/app/data/my_source.py`:

```python
from app.data.base_source import AbstractDataSource, StockData

class MySource(AbstractDataSource):
    """Fetches data from MyDataProvider."""

    @property
    def source_name(self) -> str:
        return "MyDataProvider"

    def get_price_history(self, ticker: str) -> StockData:
        # Fetch OHLCV data; return StockData with price_history=None + a
        # warning on failure — never raise.
        ...

    def get_company_info(self, ticker: str) -> StockData:
        # Fetch company metadata; return StockData with company_info={}
        # + a warning on failure — never raise.
        ...

    def get_financials(self, ticker: str) -> StockData:
        # Fetch financial statement data; return StockData with
        # financials={} + a warning on failure — never raise.
        ...
```

**2. Register it in `SourceRegistry`**

Open `backend/app/data/source_registry.py` and add your source to the
`SourceRegistry.__init__` method:

```python
from app.data.my_source import MySource

class SourceRegistry:
    def __init__(self) -> None:
        self._yahoo  = YahooFinanceSource()
        self._stooq  = StooqSource()
        self._fmp    = FMPSource()
        self._mine   = MySource()   # ← add this
```

Then wire it into `_resolve_price_history` and/or `_resolve_fundamentals` at
the appropriate priority position (after the existing fallbacks if it is a
last-resort source).

**3. Add tests**

Add a test class in `backend/tests/test_data_sources.py` that mocks the
external HTTP call and asserts that `StockData` fields are populated correctly
and that network errors are caught and converted to warnings.

---

## How to Add a New Analysis Module

The analysis layer (`backend/app/analysis/`) contains pure calculation
functions. Agents in `backend/app/agents/` call them and attach the result to
the `ReportPayload`.

**1. Create the analysis module**

Create `backend/app/analysis/my_analysis.py`:

```python
from app.data.base_source import StockData

class MyAnalyser:
    """Computes XYZ metric from stock data."""

    def analyse(self, stock_data: StockData) -> dict:
        """
        Return a dict with your metrics.
        Must never raise — return {'status': 'error', 'reason': '...'} on failure.
        """
        ...
```

**2. Create an agent wrapper**

Create `backend/app/agents/my_agent.py` that instantiates `MyAnalyser` and
calls `analyse()`. Follow the pattern of `fundamental_agent.py` or
`technical_agent.py`.

**3. Register in the orchestrator**

Open `backend/app/core/orchestrator.py` and add a pipeline step that calls
your agent and stores its result in the `ReportPayload` dict.

**4. Extend the schema**

Add the result field to `ReportPayload` in `backend/app/schemas/report.py` and
the matching TypeScript interface in `frontend/src/types/index.ts`.

**5. Display it in the UI**

Add a new panel component in `frontend/src/components/` and include it in
`frontend/src/pages/Report.tsx`.

---

## Rate Limiting (Public Deployments)

For **local or personal use**, no rate limiting is needed.

If you expose this app on a public URL, protect `POST /api/analyse` to prevent
runaway calls to Yahoo Finance, DuckDuckGo, and the Groq API. Two options:

### Option A — `slowapi` (Python, no infrastructure changes)

```bash
pip install slowapi
# Add to requirements.txt: slowapi==0.1.9
```

```python
# backend/app/main.py — add after imports
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request

limiter = Limiter(key_func=get_remote_address)

# Register on the app instance (inside create_app):
application.state.limiter = limiter
application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

```python
# backend/app/api/routes/analysis.py — decorate the analyse handler
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

limiter = Limiter(key_func=get_remote_address)

@router.post("/analyse", ...)
@limiter.limit("5/minute")          # 5 analysis requests per IP per minute
async def analyse(request: Request, body: AnalyseRequest, ...):
    ...
```

### Option B — nginx `limit_req` (no Python changes)

Add the following to `frontend/nginx.conf` — one declaration in the `server`
block and one directive inside the proxied location:

```nginx
# Declare a 10 MB shared memory zone; allow 5 requests/minute per client IP.
limit_req_zone $binary_remote_addr zone=analyse_limit:10m rate=5r/m;

# Inside the server { } block, override the /api/analyse location:
location = /api/analyse {
    limit_req zone=analyse_limit burst=2 nodelay;

    set $backend_upstream http://backend:8000;
    proxy_pass               $backend_upstream;
    proxy_http_version       1.1;
    proxy_buffering          off;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

nginx returns HTTP 429 automatically when the limit is exceeded.

---

## Ticker Symbol Format

Supported formats: standard US equity tickers (`AAPL`, `MSFT`) and
multi-class shares (`BRK.B`, `BF.B`).

The backend validates every ticker against this regex (after `.upper().strip()`):

```
^[A-Z0-9]{1,5}([.\-][A-Z]{1,2})?$
```

| Part | Meaning |
|---|---|
| `[A-Z0-9]{1,5}` | 1–5 alphanumeric characters (the base symbol) |
| `([.\-][A-Z]{1,2})?` | Optional dot or hyphen + 1–2 letters (share class suffix) |

Examples: `AAPL`, `MSFT`, `GOOGL`, `BRK.B`, `BF.B`, `BF-B`

**Not supported in v1:** international exchange suffixes (e.g. `ASML.AS`).
A helper hint is shown beneath the ticker input field in the UI.

---

*For informational purposes only. Not financial advice.*
