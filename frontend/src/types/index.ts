/**
 * TypeScript interfaces for the Stock Analysis Agent frontend.
 *
 * Every interface here mirrors a Pydantic model in backend/app/schemas/.
 * Field names, types, and optionality are kept in exact 1-to-1 correspondence
 * so that JSON responses from the API can be assigned to these types without
 * any runtime transformation.
 *
 * Backend source of truth:
 *   backend/app/schemas/analysis.py  — FundamentalMetric … SentimentResult
 *   backend/app/schemas/report.py    — NewsItem, ReportPayload, JobStatusResponse
 */

// ── Shared ─────────────────────────────────────────────────────────────────────

/** Possible states of a background analysis job. */
export type JobStatus = 'pending' | 'running' | 'complete' | 'error'

/** One of the three possible LLM recommendations. */
export type Recommendation = 'Buy' | 'Hold' | 'Sell'

// ── Fundamental analysis ───────────────────────────────────────────────────────

/**
 * A single computed fundamental metric.
 * Mirrors: backend/app/schemas/analysis.py :: FundamentalMetric
 */
export interface FundamentalMetric {
  /** Beginner-friendly display name, e.g. "Price / Earnings (P/E)". */
  label: string
  /** Raw numeric value, or null when the metric could not be computed. */
  value: number | null
  /** Unit string for display, e.g. "%", "x", "$". Null when not applicable. */
  unit: string | null
  /** One-sentence plain-language hint for beginners. Null when not supplied. */
  interpretation: string | null
}

/**
 * Output of FundamentalAnalyser.analyse() for a single ticker.
 * Mirrors: backend/app/schemas/analysis.py :: FundamentalResult
 */
export interface FundamentalResult {
  ticker: string
  pe_ratio: FundamentalMetric
  eps: FundamentalMetric
  pb_ratio: FundamentalMetric
  debt_to_equity: FundamentalMetric
  profit_margin: FundamentalMetric
  revenue_growth: FundamentalMetric
  dividend_yield: FundamentalMetric
  /** Composite fundamental health score, 0–100. */
  score: number
  /** Warning messages for any metric that could not be computed. */
  warnings: string[]
}

// ── Technical analysis ────────────────────────────────────────────────────────

/**
 * A named time-series of indicator values aligned to TechnicalResult.dates.
 * Mirrors: backend/app/schemas/analysis.py :: IndicatorSeries
 */
export interface IndicatorSeries {
  /** Display name of the indicator, e.g. "SMA 20", "RSI 14". */
  name: string
  /**
   * Ordered list of values aligned to TechnicalResult.dates.
   * null entries appear for warm-up bars where the indicator is undefined.
   */
  values: (number | null)[]
}

/**
 * Output of TechnicalAnalyser.analyse() for a single ticker.
 * Mirrors: backend/app/schemas/analysis.py :: TechnicalResult
 */
export interface TechnicalResult {
  ticker: string
  /** ISO-8601 date strings ("YYYY-MM-DD") used as the chart x-axis. */
  dates: string[]
  /** Closing price series aligned to dates. */
  close_prices: (number | null)[]

  sma_20: IndicatorSeries
  sma_50: IndicatorSeries
  sma_200: IndicatorSeries
  ema_12: IndicatorSeries
  ema_26: IndicatorSeries
  rsi_14: IndicatorSeries
  macd: IndicatorSeries
  macd_signal: IndicatorSeries
  macd_histogram: IndicatorSeries
  bb_upper: IndicatorSeries
  bb_middle: IndicatorSeries
  bb_lower: IndicatorSeries

  /** Most recent scalar values — used for the indicator snapshot table. */
  latest_close: number | null
  latest_rsi: number | null
  latest_macd: number | null
  latest_macd_signal: number | null
  latest_sma_20: number | null
  latest_sma_50: number | null
  latest_sma_200: number | null

  /** Composite technical momentum score, 0–100. */
  score: number
  warnings: string[]
}

// ── Sentiment analysis ────────────────────────────────────────────────────────

/**
 * Output of SentimentAnalyser.analyse() for a list of news headlines.
 * Mirrors: backend/app/schemas/analysis.py :: SentimentResult
 */
export interface SentimentResult {
  ticker: string
  positive_count: number
  neutral_count: number
  negative_count: number
  /** Overall sentiment score, 0 (very negative) to 100 (very positive). 50 = neutral. */
  score: number
  /** Human-readable label: "Positive", "Neutral", or "Negative". */
  label: string
  headlines_analysed: number
}

// ── News ──────────────────────────────────────────────────────────────────────

/**
 * A single cleaned news headline returned by ResearchAgent.
 * Mirrors: backend/app/schemas/report.py :: NewsItem
 */
export interface NewsItem {
  title: string
  url: string
  /** ISO date string "YYYY-MM-DD", or empty string when unavailable. */
  date: string
  /** Bare domain name, e.g. "reuters.com". */
  source: string
}

// ── Report payload ────────────────────────────────────────────────────────────

/**
 * The complete analysis result returned by GET /api/report/{job_id}
 * once the job reaches status="complete".
 * Mirrors: backend/app/schemas/report.py :: ReportPayload
 */
export interface ReportPayload {
  // ── Identity ────────────────────────────────────────────────────────────────
  job_id: string
  ticker: string
  /** ISO 8601 UTC datetime string of when the report was assembled. */
  generated_at: string
  status: JobStatus

  // ── LLM-generated text ─────────────────────────────────────────────────────
  recommendation: Recommendation
  /** 2–3 sentence beginner-friendly overview. Empty string when LLM unavailable. */
  executive_summary: string
  /** 3-sentence justification for the recommendation. */
  rationale: string
  /** Plain-language explanation of fundamentals, ≤ 150 words. */
  fundamental_explanation: string
  /** Plain-language explanation of technical indicators, ≤ 150 words. */
  technical_explanation: string
  /** 2–3 sentence prose summary of recent news headlines. Empty when unavailable. */
  news_summary: string

  // ── Structured analysis results ─────────────────────────────────────────────
  fundamental_result: FundamentalResult
  technical_result: TechnicalResult
  sentiment_result: SentimentResult
  news_items: NewsItem[]

  // ── Metadata ────────────────────────────────────────────────────────────────
  /** Names of every data source used, e.g. ["Yahoo Finance", "Stooq"]. */
  sources_used: string[]
  warnings: string[]
  /** Mandatory disclaimer — always present, never blank. */
  disclaimer: string
  /** Absolute server path to the generated PDF, or null before generation. */
  pdf_path: string | null
}

// ── In-progress status ────────────────────────────────────────────────────────

/**
 * Lightweight response returned by GET /api/report/{job_id} while the job
 * is pending or running.
 * Mirrors: backend/app/schemas/report.py :: JobStatusResponse
 */
export interface JobStatusResponse {
  status: JobStatus
  /**
   * Human-readable label of the pipeline step currently executing,
   * e.g. "Fetching data", "Analysing fundamentals & technicals".
   * null when status is "pending" or "error".
   */
  current_step: string | null
  /** Error message when status is "error"; null otherwise. */
  error: string | null
}

// ── API request / response helpers ────────────────────────────────────────────

/**
 * Response returned by POST /api/analyse.
 * Mirrors: backend/app/schemas/analysis.py :: AnalyseResponse
 */
export interface AnalyseResponse {
  job_id: string
  status: JobStatus
}

/**
 * Response returned by GET /api/validate/{ticker}.
 * Always HTTP 200 — the frontend decides how to react based on `valid`.
 * Mirrors: backend/app/schemas/analysis.py :: ValidateResponse
 */
export interface ValidateResponse {
  valid: boolean
  /** Company name when valid=true; null otherwise. */
  name: string | null
  /** Short reason string when valid=false; null otherwise. */
  reason: string | null
}
