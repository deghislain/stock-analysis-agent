# Stock Analysis Agent — Architecture & Implementation Plan

## Top-Level Overview

Build a standalone, agentic stock analysis web app for beginner investors. A user enters a stock ticker symbol, clicks "Generate Report", and receives:
1. An interactive dashboard with charts and key metrics
2. A downloadable PDF report

The system is **informational only** — it never presents output as financial advice.

**Project root:** `stock-analysis-agent`

### Technology Decisions
| Layer | Choice | Reason |
|---|---|---|
| Backend framework | FastAPI (Python) | Async, fast, consistent with sibling project |
| LLM provider | Groq (free tier) | Fast inference, same as sibling project |
| Data (primary) | yfinance (Yahoo Finance) | Free, no API key, comprehensive |
| Data (fallback 1) | Stooq via pandas-datareader | Free, no API key, price history |
| Data (fallback 2) | Financial Modeling Prep (FMP) free tier | No API key for select endpoints; provides fundamentals |
| Web research | DuckDuckGo Search (ddgs) | Free, no API key |
| PDF generation | ReportLab | Pure Python, precise control |
| Frontend framework | React + Vite + TypeScript | Modern, fast dev experience |
| Styling | Tailwind CSS | Utility-first, consistent with sibling |
| Charts | Chart.js + react-chartjs-2 + chartjs-chart-financial | Lightweight, beginner-friendly |
| HTTP client (FE) | Axios + TanStack React Query | Same as sibling project |
| Containerisation | Docker + Docker Compose | Local dev + cloud-ready |

> **Data source policy:** All fallback sources must be usable without any API key registration. Alpha Vantage is explicitly excluded because its free tier mandates a (free but required) API key, which violates the no-key requirement.

---

## Folder Structure

```
stock-analysis-agent/
├── backend/
│   ├── app/
│   │   ├── agents/                  # Agentic orchestration layer
│   │   │   ├── __init__.py
│   │   │   ├── base_agent.py        # Abstract base for all agents
│   │   │   ├── data_agent.py        # Gathers raw data + fallback logic
│   │   │   ├── fundamental_agent.py # Performs fundamental analysis
│   │   │   ├── technical_agent.py   # Performs technical analysis
│   │   │   ├── research_agent.py    # Web research / news gathering
│   │   │   └── report_agent.py      # Synthesises all analysis → report
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── dependencies.py      # FastAPI dependency injection
│   │   │   └── routes/
│   │   │       ├── __init__.py
│   │   │       ├── analysis.py      # POST /analyse, GET /status/{job_id}
│   │   │       └── report.py        # GET /report/{job_id}/pdf
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py      # Coordinates all agents end-to-end
│   │   │   ├── llm_client.py        # Groq API wrapper
│   │   │   └── job_store.py         # In-memory job state tracker
│   │   ├── data/
│   │   │   ├── __init__.py
│   │   │   ├── base_source.py       # Abstract base for data sources
│   │   │   ├── yahoo_finance.py     # Primary: yfinance wrapper
│   │   │   ├── stooq_source.py      # Fallback 1: Stooq (free, no key) — price history
│   │   │   ├── fmp_source.py        # Fallback 2: FMP free endpoints (no key) — fundamentals
│   │   │   └── source_registry.py   # Priority-ordered source list
│   │   ├── analysis/
│   │   │   ├── __init__.py
│   │   │   ├── fundamental.py       # P/E, EPS, debt, margins, etc.
│   │   │   ├── technical.py         # SMA, EMA, RSI, MACD, Bollinger
│   │   │   └── sentiment.py         # News sentiment scoring
│   │   ├── report/
│   │   │   ├── __init__.py
│   │   │   ├── pdf_generator.py     # ReportLab PDF builder
│   │   │   └── templates/           # ReportLab style definitions
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── analysis.py          # Pydantic request/response models
│   │   │   └── report.py            # Report data models
│   │   ├── config.py                # Centralised Pydantic settings
│   │   ├── logger.py                # Structured logging setup
│   │   └── main.py                  # FastAPI app entry point
│   ├── tests/
│   │   ├── test_data_sources.py
│   │   ├── test_analysis.py
│   │   ├── test_agents.py
│   │   └── test_api.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── TickerInput.tsx       # Symbol input + validate button
│   │   │   ├── ReportDashboard.tsx   # Main report view container
│   │   │   ├── ExecutiveSummary.tsx  # Buy/Hold/Sell + rationale
│   │   │   ├── FundamentalPanel.tsx  # Fundamentals with plain-language
│   │   │   ├── TechnicalPanel.tsx    # Technical charts + explanations
│   │   │   ├── NewsPanel.tsx         # Recent news + sentiment
│   │   │   ├── DataSourcesBadge.tsx  # Which sources were used
│   │   │   ├── WarningFlags.tsx      # Missing/conflicting data alerts
│   │   │   ├── LoadingSpinner.tsx    # Progress indicator
│   │   │   └── charts/
│   │   │       ├── PriceChart.tsx    # Line chart: price history
│   │   │       ├── VolumeChart.tsx   # Bar chart: volume
│   │   │       ├── RSIChart.tsx      # Line chart: RSI
│   │   │       └── MetricsRadar.tsx  # Radar: fundamental score
│   │   ├── pages/
│   │   │   ├── Home.tsx              # Landing / ticker entry page
│   │   │   └── Report.tsx            # Full report page
│   │   ├── services/
│   │   │   └── api.ts                # Axios API client
│   │   ├── hooks/
│   │   │   └── useAnalysis.ts        # TanStack Query hook for analysis
│   │   ├── types/
│   │   │   └── index.ts              # TypeScript type definitions
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── Dockerfile
├── docs/
│   └── architecture.md
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## System Architecture Diagram (described)

```
User Browser
    │
    │  0. GET /api/validate/{ticker}  → {valid: true/false, name: "Apple Inc."}
    │  1. POST /api/analyse {ticker}  → {job_id, status: "pending"}
    ▼
FastAPI Backend
    │
    ├── Orchestrator
    │       │
    │       ├── DataAgent ──────── Yahoo Finance (primary, no key)
    │       │                       Stooq (fallback 1, no key) — price history
    │       │                       FMP free (fallback 2, no key) — fundamentals
    │       │
    │       ├── FundamentalAgent ── analysis/fundamental.py
    │       │
    │       ├── TechnicalAgent ──── analysis/technical.py
    │       │
    │       ├── ResearchAgent ───── DuckDuckGo Search (ddgs, no key)
    │       │                       News sentiment scoring
    │       │
    │       └── ReportAgent ──────── Groq LLM (plain-language summaries)
    │                                 ReportLab (PDF)
    │
    │  2. GET /api/report/{job_id}     → JSON dashboard data
    │  3. GET /api/report/{job_id}/pdf → PDF file download
    ▼
User Browser (React Dashboard + PDF download)
```

---

## Sub-Tasks

---

### Sub-Task 1 — Project Scaffolding & Configuration
**Status:** [ ] pending

**Intent:**
Set up the complete project skeleton: folder structure, dependency files, configuration, logging, Docker, and environment template. This is the foundation everything else builds on.

**Expected Outcomes:**
- `stock-analysis-agent/` directory exists with all folders
- `backend/requirements.txt` lists all Python dependencies (including `pandas-datareader` for Stooq)
- `backend/app/config.py` has all settings via Pydantic Settings
- `backend/app/logger.py` provides structured logging
- `backend/app/main.py` boots a minimal FastAPI app (health check route only); PDF cleanup scheduled via FastAPI `lifespan` event
- `frontend/package.json` lists all JS dependencies
- `frontend/vite.config.ts`, `tailwind.config.js`, `tsconfig.json` configured
- `docker-compose.yml` wires backend + frontend
- `.env.example` documents all required environment variables
- `README.md` explains how to run the project

**Coding Standard (applies to all sub-tasks):**
Every public class and every public function/method must have a docstring that explains its purpose in one plain sentence. This is not optional — the audience includes junior developers who are reading the code for the first time.

**Todo List:**
1. Create all directories (backend/app/agents, api/routes, core, data, analysis, report/templates, schemas, tests; frontend/src/components/charts, pages, services, hooks, types)
2. Write `backend/requirements.txt` with: fastapi, uvicorn, yfinance, pandas, numpy, pandas-datareader, ta (technical analysis), reportlab, groq, duckduckgo-search, httpx, pydantic-settings, python-dotenv, pytest, pytest-asyncio
3. Write `backend/app/config.py` — Pydantic Settings with: APP_NAME, DEBUG, GROQ_API_KEY, GROQ_MODEL, CORS_ORIGINS, DATA_CACHE_TTL_SECONDS, PDF_OUTPUT_DIR
4. Write `backend/app/logger.py` — structured logger using Python `logging`, JSON format in production
5. Write `backend/app/main.py` — FastAPI app with CORS middleware, health check `GET /health`, include routers (stubs for now); use `lifespan` context manager to: (a) create `PDF_OUTPUT_DIR` at startup, (b) launch PDF cleanup background task (asyncio loop, runs every 30 min, deletes files older than 1 hour)
6. Write `frontend/package.json` with all deps: react, react-dom, react-router-dom, axios, @tanstack/react-query, chart.js, react-chartjs-2, chartjs-chart-financial, chartjs-adapter-date-fns, tailwindcss, typescript, vite
7. Write `frontend/vite.config.ts`, `tailwind.config.js`, `tsconfig.json`
8. Write `frontend/src/main.tsx` and `frontend/src/App.tsx` (minimal router shell)
9. Write `docker-compose.yml`
10. Write `.env.example` and `README.md`

**Relevant Context:**
- Follow the same Pydantic Settings pattern as `backend/app/config.py` in the sibling project (528-line reference)
- CORS pattern from sibling project's `main.py`
- Same Docker multi-stage build pattern as sibling `frontend/Dockerfile`
- PDF cleanup uses `asyncio.create_task()` inside the `lifespan` function — no APScheduler dependency needed

---

### Sub-Task 2 — Data Layer: Sources & Fallback Registry
**Status:** [ ] pending

**Intent:**
Build the data acquisition layer with a priority-ordered fallback chain. The system tries Yahoo Finance first; if data is incomplete, it falls back to Stooq (price history), then FMP free endpoints (fundamentals). All three sources are completely free and require no API key registration. Each source implements the same abstract interface so the agent layer never needs to care which source is active.

**Expected Outcomes:**
- `data/base_source.py` defines `AbstractDataSource` with methods: `get_price_history()`, `get_company_info()`, `get_financials()`
- `data/yahoo_finance.py` implements the interface using `yfinance` (primary: price history + fundamentals)
- `data/stooq_source.py` implements the interface using `pandas_datareader` Stooq endpoint (fallback 1: price history only; fundamentals/financials marked unavailable)
- `data/fmp_source.py` implements the interface using FMP free JSON endpoints via `httpx` (fallback 2: fundamentals/company info; no API key required for the free profile and quote endpoints)
- `data/source_registry.py` holds the ordered list and exposes `get_data_with_fallback(ticker)` which returns merged data + a list of which sources were actually used + a list of warning flags for missing fields
- All sources handle network errors gracefully and return `None` fields rather than raising
- **Warning message for fundamentals-unavailable scenario:** when neither Yahoo nor FMP can provide company_info/financials, `source_registry` appends the warning: `"Fundamental data is unavailable for this ticker. Fundamental analysis section will be incomplete."` — this propagates to `WarningFlags` in the UI and to the PDF warnings page

**Todo List:**
1. Write `data/base_source.py` — define `StockData` dataclass (price_history: DataFrame, company_info: dict, financials: dict, source_name: str, warnings: list[str]); add docstring to class and each field
2. Write `data/yahoo_finance.py` — wrap `yfinance.Ticker`, populate all `StockData` fields, catch all exceptions, set warnings for any None/empty fields
3. Write `data/stooq_source.py` — use `pandas_datareader.data.DataReader` with `stooq` source for price history; set `company_info = {}` and `financials = {}` and append warning: `"Stooq provides price history only. Fundamental data not available from this source."`
4. Write `data/fmp_source.py` — use FMP free endpoints `https://financialmodelingprep.com/api/v3/profile/{ticker}` and `https://financialmodelingprep.com/api/v3/ratios-ttm/{ticker}` via `httpx` (no API key); populate company_info and financials; set price_history as unavailable with warning
5. Write `data/source_registry.py` — `SourceRegistry` class with ordered list [Yahoo, Stooq, FMP]; `get_data_with_fallback(ticker)` tries each, merges results (Yahoo price history preferred; FMP fundamentals used if Yahoo fundamentals empty), returns combined `StockData` + `sources_used` list
6. Write unit tests in `tests/test_data_sources.py` with mocked HTTP calls

**Relevant Context:**
- `StockData` dataclass is the contract between data layer and analysis layer — field names must be stable
- Warning flags flow all the way to the frontend `WarningFlags` component
- `sources_used` flows to the frontend `DataSourcesBadge` component
- Stooq fallback covers the "Yahoo completely down" scenario for charts/technical analysis but cannot supply fundamentals — this is acceptable and must be surfaced as a warning, not a hard error
- FMP free profile endpoint returns: `companyName`, `sector`, `industry`, `marketCap`, `price`, `description` — no key needed; document this in a comment in `fmp_source.py`

---

### Sub-Task 3 — Analysis Layer: Fundamental & Technical
**Status:** [ ] pending

**Intent:**
Implement the two core analysis modules. Both take a `StockData` object and return structured, plain-language-ready analysis results. Calculations are deterministic (no LLM here) — the LLM only adds plain-language explanations in the report layer.

**Expected Outcomes:**
- `analysis/fundamental.py` computes: P/E ratio, EPS, P/B ratio, debt-to-equity, profit margin, revenue growth, dividend yield — each with a beginner-friendly label and a raw value
- `analysis/technical.py` computes: SMA(20), SMA(50), SMA(200), EMA(12), EMA(26), RSI(14), MACD + signal line, Bollinger Bands(20) — using the `ta` library
- Both modules return a `FundamentalResult` / `TechnicalResult` Pydantic model
- Both modules include a simple `score` (0–100) that feeds the executive summary recommendation
- Both modules populate `warnings` for any metric that could not be computed
- `analysis/sentiment.py` scores news headlines (positive/neutral/negative count + overall sentiment score)

**Todo List:**
1. Write `schemas/analysis.py` — define `FundamentalResult`, `TechnicalResult`, `SentimentResult`, `AnalysisResult` (aggregate) Pydantic models
2. Write `analysis/fundamental.py` — `FundamentalAnalyser.analyse(stock_data: StockData) -> FundamentalResult`; compute each metric from `stock_data.company_info` / `stock_data.financials`; add warning if metric unavailable
3. Write `analysis/technical.py` — `TechnicalAnalyser.analyse(stock_data: StockData) -> TechnicalResult`; use `ta` library on `price_history` DataFrame; return latest indicator values + series for charting
4. Write `analysis/sentiment.py` — `SentimentAnalyser.analyse(news_items: list[dict]) -> SentimentResult`; simple keyword-based scoring (no external model needed)
5. Write unit tests in `tests/test_analysis.py` using synthetic DataFrames

**Relevant Context:**
- `ta` library (Technical Analysis library for Python) wraps pandas operations — use `ta.trend`, `ta.momentum`, `ta.volatility`
- Scoring logic: fundamental score + technical score → weighted average → map to Buy/Hold/Sell
- Chart series data (price history + indicator values over time) lives in `TechnicalResult` and is returned to the frontend as JSON arrays

---

### Sub-Task 4 — Agent Layer: Data, Research, Fundamental, Technical, Report Agents
**Status:** [ ] pending

**Intent:**
Wrap the data and analysis modules in agents with a consistent interface. Add the `ResearchAgent` (DuckDuckGo web search + news) and `ReportAgent` (Groq LLM plain-language generation). The `Orchestrator` calls all agents in sequence and assembles the final report payload.

**Expected Outcomes:**
- `agents/base_agent.py` defines `BaseAgent` abstract class with `run()` method
- `agents/data_agent.py` calls `source_registry.get_data_with_fallback()` → returns `StockData`
- `agents/fundamental_agent.py` calls `FundamentalAnalyser` → returns `FundamentalResult`
- `agents/technical_agent.py` calls `TechnicalAnalyser` → returns `TechnicalResult`
- `agents/research_agent.py` uses `duckduckgo_search` (ddgs) to fetch recent news headlines for the ticker; returns list of news items with title, URL, date
- `agents/report_agent.py` calls Groq LLM to generate: executive summary (Buy/Hold/Sell + 3-sentence rationale), plain-language fundamental explanation, plain-language technical explanation
- `core/orchestrator.py` runs all agents in order, assembles `ReportPayload` schema, stores result in `job_store`
- `core/job_store.py` — simple in-memory dict keyed by `job_id` (UUID), storing status + result

**Todo List:**
1. Write `agents/base_agent.py` — `BaseAgent` with abstract `async run(**kwargs) -> dict`
2. Write `agents/data_agent.py` — wraps `SourceRegistry`, validates ticker symbol exists, raises `ValueError` for unknown ticker
3. Write `agents/research_agent.py` — uses `DDGS().text(f"{ticker} stock news", max_results=10)`, returns cleaned list of news items
4. Write `agents/fundamental_agent.py` — thin wrapper around `FundamentalAnalyser`
5. Write `agents/technical_agent.py` — thin wrapper around `TechnicalAnalyser`
6. Write `agents/report_agent.py` — builds Groq prompt from analysis results, calls `llm_client.py`, parses structured response (executive summary + plain-language sections); has a graceful fallback if Groq API is unavailable (returns template-based text)
7. Write `core/llm_client.py` — `GroqClient` wrapping the Groq Python SDK; `async generate(prompt: str) -> str`
8. Write `core/job_store.py` — `JobStore` with `create_job()`, `update_job()`, `get_job()` using a dict; thread-safe with asyncio Lock
9. Write `core/orchestrator.py` — `Orchestrator.run(ticker: str, job_id: str)` calls agents in sequence, updates job status at each step, stores final `ReportPayload` in job store
10. Write unit tests in `tests/test_agents.py`

**Relevant Context:**
- Groq prompt engineering: instruct it to respond in JSON with keys: `executive_summary`, `recommendation` (Buy/Hold/Sell), `rationale` (3 sentences), `fundamental_explanation` (plain language, max 150 words), `technical_explanation` (plain language, max 150 words)
- Disclaimer text ("For informational purposes only. Not financial advice.") must be baked into every Groq prompt and into the report schema
- `job_id` is a UUID string generated at `POST /api/analyse` time; frontend polls `GET /api/report/{job_id}` until status = "complete"

---

### Sub-Task 5 — API Layer: Routes & Schemas
**Status:** [ ] pending

**Intent:**
Expose the orchestrator via FastAPI REST endpoints. The frontend first validates the ticker, then posts it to start analysis, polls for status, fetches the JSON report, and downloads the PDF.

**Expected Outcomes:**
- `GET /api/validate/{ticker}` — **new, called by the frontend before queuing any job**; checks format (regex) then calls `yfinance.Ticker(ticker).info` to confirm the symbol exists; returns `{valid: true, name: "Apple Inc."}` or `{valid: false, reason: "Symbol not found"}` within ~1s; returns 200 in both cases (never 4xx — let the frontend decide how to display it)
- `POST /api/analyse` — validates ticker format, creates job, fires orchestrator as background task, returns `{job_id, status: "pending"}`
- `GET /api/report/{job_id}` — returns full `ReportPayload` JSON when status = "complete", or `{status: "pending"|"running"|"error", current_step?: str}` otherwise
- `GET /api/report/{job_id}/pdf` — streams the PDF file as a download
- `GET /health` — returns `{status: "ok"}`
- All routes have proper error responses (404 for unknown job, 422 for invalid ticker format, 500 with safe error message)
- Input validation: ticker must be 1–10 alphanumeric characters + optional dot/hyphen (regex `^[A-Z0-9]{1,5}([.\-][A-Z]{1,2})?$` after `.upper().strip()`) — supports `BRK.B`, `BF.B` style tickers

**ReportPayload schema** (explicit field list — all sub-tasks must respect these names):
```python
class NewsItem(BaseModel):
    title: str
    url: str
    date: str          # ISO date string
    source: str        # domain name

class ReportPayload(BaseModel):
    job_id: str
    ticker: str
    generated_at: str                        # ISO datetime
    status: str                              # "complete" | "error"
    recommendation: str                      # "Buy" | "Hold" | "Sell"
    rationale: str                           # 3-sentence LLM output
    fundamental_result: FundamentalResult
    technical_result: TechnicalResult
    sentiment_result: SentimentResult
    news_items: list[NewsItem]               # from ResearchAgent
    fundamental_explanation: str             # plain-language LLM output
    technical_explanation: str              # plain-language LLM output
    sources_used: list[str]                  # e.g. ["Yahoo Finance", "Stooq"]
    warnings: list[str]                      # all warnings from data + analysis layers
    disclaimer: str                          # hardcoded: "For informational purposes only. Not financial advice."
    pdf_path: str | None                     # set after PDF generation
```

**Todo List:**
1. Write `schemas/report.py` — define `NewsItem` and `ReportPayload` as above; define `JobStatusResponse` for in-progress responses
2. Write `schemas/analysis.py` additions — `AnalyseRequest` (ticker: str), `AnalyseResponse` (job_id: str, status: str), `ValidateResponse` (valid: bool, name: str | None, reason: str | None)
3. Write `api/routes/analysis.py` — `GET /api/validate/{ticker}` endpoint; `POST /api/analyse` endpoint; validate ticker with regex; create job in job_store; launch `orchestrator.run()` as `BackgroundTasks`; return job_id
4. Write `api/routes/report.py` — `GET /api/report/{job_id}` (JSON) and `GET /api/report/{job_id}/pdf` (FileResponse)
5. Write `api/dependencies.py` — provide `Orchestrator` and `JobStore` as FastAPI dependencies (singleton pattern)
6. Update `main.py` to include both routers under `/api` prefix
7. Write integration tests in `tests/test_api.py` using `TestClient`

**Relevant Context:**
- Use FastAPI `BackgroundTasks` for async orchestration — keeps the POST response instant
- `FileResponse` from `fastapi.responses` for PDF streaming
- Ticker regex: `^[A-Z0-9]{1,5}([.\-][A-Z]{1,2})?$` after `.upper().strip()` — covers standard US tickers and common multi-class formats like `BRK.B`; document this constraint in a comment and in the README
- The validate endpoint is lightweight and synchronous (fast yfinance metadata call) — no background task needed
- `current_step` in the in-progress response feeds the frontend's `LoadingSpinner` step labels directly

---

### Sub-Task 6 — PDF Report Generation
**Status:** [ ] pending

**Intent:**
Build the ReportLab PDF generator that takes a completed `ReportPayload` and produces a well-structured, beginner-friendly PDF with styled sections, key metrics table, and a disclaimer footer.

**Expected Outcomes:**
- `report/pdf_generator.py` — `PDFGenerator.generate(payload: ReportPayload, output_path: str)` produces a PDF
- PDF structure: Cover page (ticker, date, disclaimer), Executive Summary (recommendation badge + rationale), Fundamental Analysis (metrics table + plain-language explanation), Technical Analysis (indicator table + plain-language explanation), News Summary, Data Sources Used, Warning Flags (if any), Disclaimer footer on every page
- PDF is saved to `PDF_OUTPUT_DIR` (configured in config.py) with filename `{ticker}_{job_id}.pdf`
- File is cleaned up after 1 hour (simple background task)
- Styling: clean, minimal, readable — uses ReportLab `Paragraph`, `Table`, `Spacer`, `colors` — no raw X/Y coordinate drawing

**Todo List:**
1. Write `report/templates/styles.py` — define ReportLab `ParagraphStyle` and `TableStyle` objects for headings, body, metrics tables, recommendation badges (green=Buy, yellow=Hold, red=Sell)
2. Write `report/pdf_generator.py` — `PDFGenerator` class; `generate()` method builds a `SimpleDocTemplate` with `Story` list of flowables; one method per section (cover, executive_summary, fundamental, technical, news, sources, warnings)
3. Add PDF cleanup background task in `main.py` (runs every 30 minutes, deletes files older than 1 hour)
4. Wire `pdf_generator.generate()` call into the orchestrator as the final step after all agents complete

**Relevant Context:**
- ReportLab `SimpleDocTemplate` + `Story` pattern is the cleanest approach — avoid `canvas` raw drawing
- `PDF_OUTPUT_DIR` defaults to `/tmp/stock_reports/` — created at startup if not exists
- The PDF route in Sub-Task 5 uses `fastapi.responses.FileResponse` pointing to this path

---

### Sub-Task 7 — Frontend: Dashboard UI
**Status:** [ ] pending

**Intent:**
Build the React frontend: a simple home page with a ticker input (with inline validation feedback), a report dashboard page with charts and panels, a loading state with progress steps, and a PDF download button.

**Expected Outcomes:**
- `pages/Home.tsx` — centered card with app title, subtitle ("Informational analysis only — not financial advice"), ticker input field with inline validation, "Generate Report" button (disabled until ticker is validated as valid)
- `pages/Report.tsx` — shows loading spinner with step labels while job is pending/running; when complete renders full dashboard
- `components/TickerInput.tsx` — calls `GET /api/validate/{ticker}` on blur/enter; shows green checkmark + company name on success, red message "Symbol not found" on failure; disables Generate Report button while validating or invalid
- `components/ExecutiveSummary.tsx` — prominent Buy/Hold/Sell badge (green/yellow/red), 3-sentence rationale, disclaimer text
- `components/FundamentalPanel.tsx` — metrics table (P/E, EPS, P/B, etc.) + plain-language explanation paragraph
- `components/TechnicalPanel.tsx` — hosts PriceChart + VolumeChart + RSIChart + plain-language explanation
- `components/NewsPanel.tsx` — list of recent news items with title, source, date, link
- `components/charts/PriceChart.tsx` — Chart.js line chart: closing price + SMA(20) + SMA(50) over 6 months
- `components/charts/VolumeChart.tsx` — Chart.js bar chart: daily trading volume over same 6-month window; helps beginners understand trading activity
- `components/charts/RSIChart.tsx` — Chart.js line chart: RSI(14) with overbought(70)/oversold(30) reference lines
- `components/charts/MetricsRadar.tsx` — Chart.js radar chart: plots normalised scores for P/E, P/B, debt-to-equity, profit margin, revenue growth (0–100 scale); gives beginners a visual "health snapshot" of the company; shown inside FundamentalPanel
- `components/DataSourcesBadge.tsx` — small pills showing which data sources were used
- `components/WarningFlags.tsx` — yellow warning banners for missing/conflicting data
- `hooks/useAnalysis.ts` — TanStack Query hook: posts ticker, polls status every 2s, returns report data
- PDF download button calls `GET /api/report/{job_id}/pdf`

**Todo List:**
1. Write `types/index.ts` — TypeScript interfaces matching `ReportPayload` backend schema exactly (include `NewsItem`, `FundamentalResult`, `TechnicalResult`, `SentimentResult`, `ReportPayload`, `JobStatusResponse`)
2. Write `services/api.ts` — `validateTicker(ticker)`, `analyseStock(ticker)`, `getReport(jobId)`, `getPdfUrl(jobId)` functions using Axios
3. Write `hooks/useAnalysis.ts` — `useAnalysis(ticker)` hook: mutation to start job, polling query with 2s refetch until status="complete"; expose `currentStep` from the in-progress response to feed the loading spinner
4. Write `components/TickerInput.tsx` — input field, calls `validateTicker` on blur and on Enter; shows inline validation state (validating spinner / green name / red error); disables Generate Report button unless `valid === true`
5. Write `components/LoadingSpinner.tsx` — shows `currentStep` from the job status response (e.g. "Gathering data…", "Analysing fundamentals…", "Analysing technicals…", "Researching news…", "Generating report…")
6. Write `components/ExecutiveSummary.tsx` — includes disclaimer text below the rationale
7. Write `components/charts/PriceChart.tsx` — register Chart.js components, render line chart with SMA(20) and SMA(50) overlays
8. Write `components/charts/VolumeChart.tsx` — bar chart; bars coloured green when price closed up, red when down
9. Write `components/charts/RSIChart.tsx` — RSI line + reference lines at 30 and 70 + shaded overbought/oversold bands
10. Write `components/charts/MetricsRadar.tsx` — radar chart with 5 axes; show a "data unavailable" placeholder when fundamental scores are missing
11. Write `components/FundamentalPanel.tsx` — includes MetricsRadar + metrics table + plain-language explanation
12. Write `components/TechnicalPanel.tsx` — includes PriceChart + VolumeChart + RSIChart + plain-language explanation
13. Write `components/NewsPanel.tsx`
14. Write `components/DataSourcesBadge.tsx` and `components/WarningFlags.tsx`
15. Write `pages/Home.tsx` and `pages/Report.tsx`
16. Write `App.tsx` with React Router routes: `/` → Home, `/report/:jobId` → Report
17. Apply Tailwind styling throughout — clean, light theme

**Relevant Context:**
- Polling interval: 2 seconds; stop polling when status = "complete" or "error"
- TanStack Query `refetchInterval` option handles polling cleanly
- All disclaimer text ("For informational purposes only. Not financial advice.") must appear in the UI — in the hero subtitle, in ExecutiveSummary, and in the PDF download area
- Chart.js requires component registration: `Chart.register(...)` in main.tsx or per-chart file
- `TickerInput` calls `validateTicker` — debounce is not needed; call on blur and on Enter keypress only
- VolumeChart bar colouring: compare `close[i]` vs `close[i-1]`; use green (`#16a34a`) for up days, red (`#dc2626`) for down days

---

### Sub-Task 8 — Docker, Environment, Final Wiring & README
**Status:** [ ] pending

**Intent:**
Finalise Docker configuration, environment variables, wire everything together end-to-end, and write the README so a junior developer can get the project running in under 5 minutes.

**Expected Outcomes:**
- `docker-compose.yml` boots backend (port 8000) and frontend (port 5173) with correct env vars
- `backend/Dockerfile` — Python 3.12 slim, installs requirements, runs uvicorn
- `frontend/Dockerfile` — multi-stage: Node build → nginx serve
- `.env.example` documents GROQ_API_KEY, DEBUG, CORS_ORIGINS, PDF_OUTPUT_DIR
- `README.md` — setup instructions, architecture overview, how to add a new data source, how to extend analysis
- End-to-end smoke test: enter "AAPL", click Generate Report, see dashboard, download PDF

**Todo List:**
1. Write `backend/Dockerfile`
2. Write `frontend/Dockerfile` (multi-stage)
3. Write `frontend/nginx.conf`
4. Finalise `docker-compose.yml` with health checks and volume for PDF output dir
5. Write `.env.example`
6. Write `README.md` with: prerequisites, quick start (3 commands), environment variables table, architecture diagram (ASCII), how to add a new data source, how to add a new analysis module, disclaimer notice, **rate-limiting note** (advise wrapping with nginx rate limit or using `slowapi` if exposing publicly)

**Relevant Context:**
- Follow the same multi-stage Dockerfile pattern as the sibling project's `frontend/Dockerfile`
- Backend needs a volume mount for `PDF_OUTPUT_DIR` so PDFs persist across container restarts (optional but good practice)
- CORS_ORIGINS in production should match the frontend container hostname
- Rate limiting: for local/personal use no rate limiting is required. For any public deployment, document using `slowapi` (`pip install slowapi`) on the `/api/analyse` route (e.g. 5 requests/minute per IP) to prevent runaway external API calls

---

## Design Decisions & Rationale

### Why async job polling instead of WebSockets?
The analysis pipeline takes 10–30 seconds (LLM call + data fetching). A simple POST → job_id → poll pattern is easier to implement, debug, and explain to a junior developer than WebSockets, while achieving the same UX result.

### Why in-memory job store instead of a database?
No persistent history is needed — reports are ephemeral (generated on demand, downloaded, discarded). A database would add complexity without value. The in-memory store is thread-safe via asyncio Lock.

### Why not stream the LLM response?
Streaming requires a WebSocket or SSE connection and complicates the frontend significantly. Since the full analysis is assembled before the LLM call, a single blocking Groq call is simpler and fast enough.

### Why separate data layer from agent layer?
The data layer is a pure I/O concern (fetch + normalise). The agent layer is an orchestration concern (decide what to do, handle errors, produce structured output). Keeping them separate makes each individually testable and extensible.

### Why Stooq + FMP instead of Alpha Vantage as fallbacks?
Alpha Vantage's free tier requires API key registration, which violates the "no API key" requirement. Stooq is fully anonymous and provides reliable OHLCV price history. FMP's free profile and ratios endpoints work without a key and cover the fundamental data gap that Stooq cannot fill.

### Disclaimer enforcement
The disclaimer "For informational purposes only. Not financial advice." is enforced at three levels:
1. Baked into every Groq prompt (LLM cannot omit it)
2. Hardcoded in `ReportPayload.disclaimer` field
3. Rendered in both the frontend UI and every page of the PDF

### Groq LLM fallback template
If the Groq API is unavailable (network error, rate limit, or missing key), `report_agent.py` returns a template-based response. The fallback text lives as a constant in `agents/report_agent.py`:
```python
GROQ_FALLBACK_TEMPLATE = {
    "recommendation": "Hold",
    "rationale": (
        "Automated narrative generation is temporarily unavailable. "
        "The raw metrics are shown below so you can review the data directly. "
        "Please try again later for a full plain-language explanation."
    ),
    "fundamental_explanation": "Plain-language explanation unavailable. See the metrics table above.",
    "technical_explanation": "Plain-language explanation unavailable. See the indicator table above.",
}
```
This ensures the dashboard and PDF always render completely even without an LLM response. A `WarningFlags` entry `"AI-generated explanation unavailable — raw data shown only."` is added to the payload warnings list.

### Ticker symbol scope
The ticker regex `^[A-Z0-9]{1,5}([.\-][A-Z]{1,2})?$` intentionally covers standard US equity tickers (1–5 uppercase letters) and common multi-class share formats (`BRK.B`, `BF.B`). International exchange suffixes (e.g. `ASML.AS`) are not supported in v1. This limitation is documented in the README and displayed as a helper hint beneath the ticker input field in the UI.

### PDF cleanup mechanism
PDF cleanup is implemented as an `asyncio` task launched inside FastAPI's `lifespan` context manager (not a startup event, not APScheduler). The task loops every 30 minutes and uses `os.scandir` to delete `.pdf` files in `PDF_OUTPUT_DIR` older than 3600 seconds. This requires zero additional dependencies.
