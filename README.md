# Stock Analysis Agent

Beginner-friendly, agentic stock analysis. Enter a ticker symbol and receive
an interactive dashboard and a downloadable PDF report — powered by Yahoo
Finance, Groq LLM, and Chart.js.

> **Disclaimer:** This tool is for informational purposes only.
> It does **not** constitute financial advice. Always do your own research
> before making any investment decision.

---

## Prerequisites

| Tool | Minimum version |
|---|---|
| Python | 3.10 |
| Node.js | 18 |
| npm | 9 |
| Docker + Docker Compose | 24 / 2.20 _(optional, for containerised run)_ |

---

## Quick Start (local, no Docker)

```bash
# 1. Clone and enter the repo
git clone <repo-url> stock-analysis-agent
cd stock-analysis-agent

# 2. Configure environment
cp .env.example .env
#    → open .env and set GROQ_API_KEY

# 3. Start the backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 4. Start the frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## Quick Start (Docker Compose)

```bash
cp .env.example .env
# → open .env and set GROQ_API_KEY

docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| Swagger docs | http://localhost:8000/docs |

---

## Environment Variables

All variables are read from `.env` (copy from `.env.example`).

| Variable | Default | Required | Description |
|---|---|---|---|
| `GROQ_API_KEY` | _(empty)_ | **Yes** | Groq API key for LLM summaries. Get one free at [console.groq.com](https://console.groq.com) |
| `GROQ_MODEL` | `llama3-8b-8192` | No | Groq model ID |
| `DEBUG` | `false` | No | Verbose logging + detailed errors |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | No | Allowed frontend origins (JSON array) |
| `PDF_OUTPUT_DIR` | `/tmp/stock_reports` | No | Where PDFs are stored temporarily |
| `DATA_CACHE_TTL_SECONDS` | `300` | No | How long fetched data is cached |

---

## Architecture

```
User Browser
    │
    │  GET /api/validate/{ticker}   →  {valid, name}
    │  POST /api/analyse {ticker}   →  {job_id, status: "pending"}
    │  GET /api/report/{job_id}     →  ReportPayload JSON
    │  GET /api/report/{job_id}/pdf →  PDF file download
    ▼
FastAPI Backend (port 8000)
    │
    └── Orchestrator
            │
            ├── DataAgent ────────  Yahoo Finance  (primary,   no key)
            │                       Stooq          (fallback 1, no key) — price history
            │                       FMP free API   (fallback 2, no key) — fundamentals
            │
            ├── FundamentalAgent ─  P/E, EPS, P/B, debt-to-equity, margins
            │
            ├── TechnicalAgent ───  SMA, EMA, RSI, MACD, Bollinger Bands
            │
            ├── ResearchAgent ────  DuckDuckGo news search (no key)
            │
            └── ReportAgent ──────  Groq LLM → plain-language summaries
                                    ReportLab  → PDF

React Frontend (port 5173 / 80)
    Ticker input → polling → Dashboard (charts + panels) + PDF download
```

### Data fallback policy

All data sources are completely free and require **no API key registration**:

1. **Yahoo Finance** (`yfinance`) — primary source for price history and fundamentals
2. **Stooq** (`pandas-datareader`) — fallback for price/OHLCV history when Yahoo is unavailable
3. **FMP free endpoints** (`httpx`) — fallback for fundamental data (profile, ratios)

Alpha Vantage is explicitly excluded — its free tier requires key registration.

---

## Project Structure

```
stock-analysis-agent/
├── backend/
│   ├── app/
│   │   ├── agents/        # Orchestration layer (data, fundamental, technical, research, report)
│   │   ├── analysis/      # Pure calculation modules (fundamental, technical, sentiment)
│   │   ├── api/routes/    # FastAPI route handlers
│   │   ├── core/          # Orchestrator, LLM client, job store
│   │   ├── data/          # Data source implementations + fallback registry
│   │   ├── report/        # PDF generator (ReportLab)
│   │   ├── schemas/       # Pydantic request/response models
│   │   ├── config.py      # Centralised settings (Pydantic Settings)
│   │   ├── logger.py      # Structured JSON logging
│   │   └── main.py        # FastAPI entry point + lifespan
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/    # UI building blocks (panels, charts, badges)
│   │   ├── hooks/         # useAnalysis — TanStack Query polling hook
│   │   ├── pages/         # Home (ticker entry) + Report (dashboard)
│   │   ├── services/      # Axios API client
│   │   └── types/         # TypeScript interfaces matching backend schemas
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Running the Tests

```bash
cd backend

# Activate your virtual environment first, then:
python -m pytest                                        # all tests, quiet
python -m pytest -v                                     # verbose
python -m pytest --cov=app --cov-report=term-missing    # with coverage
```

Current coverage: **100%** across `config.py`, `logger.py`, `main.py`.

---

## How to Add a New Data Source

1. Create `backend/app/data/my_source.py` and implement `AbstractDataSource`:

```python
from app.data.base_source import AbstractDataSource, StockData

class MySource(AbstractDataSource):
    """Fetches data from MyDataProvider (free, no key)."""

    def get_price_history(self, ticker: str) -> StockData: ...
    def get_company_info(self, ticker: str) -> StockData: ...
    def get_financials(self, ticker: str) -> StockData: ...
```

2. Register it in `backend/app/data/source_registry.py`:

```python
from app.data.my_source import MySource

# Add to the ordered fallback list:
SOURCES = [YahooFinanceSource, StooqSource, FMPSource, MySource]
```

3. Add unit tests in `backend/tests/test_data_sources.py` with mocked HTTP calls.

---

## How to Add a New Analysis Module

1. Create `backend/app/analysis/my_analysis.py`:

```python
from app.data.base_source import StockData

class MyAnalyser:
    """Computes XYZ metric from stock data."""

    def analyse(self, stock_data: StockData) -> dict:
        ...
```

2. Create a thin agent wrapper in `backend/app/agents/my_agent.py` that calls it.

3. Register the agent in `backend/app/core/orchestrator.py` so it runs as part of the pipeline.

4. Add the result field to `ReportPayload` in `backend/app/schemas/report.py` and the matching TypeScript interface in `frontend/src/types/index.ts`.

---

## Rate Limiting (Public Deployments)

For **local or personal use**, no rate limiting is needed.

If you expose this app publicly, protect the `/api/analyse` route to prevent
runaway calls to Yahoo Finance and the Groq API:

**Option A — Python (`slowapi`)**

```bash
pip install slowapi
```

```python
# In backend/app/main.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/api/analyse")
@limiter.limit("5/minute")
async def analyse(request: Request, ...): ...
```

**Option B — nginx rate limiting** (already in `frontend/nginx.conf`)

```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=5r/m;

location /api/analyse {
    limit_req zone=api burst=2 nodelay;
    proxy_pass http://backend:8000;
}
```

---

## Ticker Symbol Format

Supported formats: standard US equity tickers (`AAPL`, `MSFT`) and
multi-class shares (`BRK.B`, `BF.B`).

**Not supported in v1:** international exchange suffixes (e.g. `ASML.AS`).
A helper hint is shown beneath the ticker input field in the UI.

---

*For informational purposes only. Not financial advice.*
