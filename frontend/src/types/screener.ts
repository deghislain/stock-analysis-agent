/**
 * TypeScript interfaces for the stock screener feature.
 * Mirror: backend/app/schemas/screener.py
 */

// ── Request ────────────────────────────────────────────────────────────────────

export interface ScreenerRequest {
  min_price: number
  max_price: number
  industry: string
}

// ── Response ───────────────────────────────────────────────────────────────────

/** One row of the undervalued-growth criteria legend. */
export interface ScreenerCriterion {
  label: string
  threshold: string
  rationale: string
}

/** A single stock that has passed all undervalued-growth criteria. */
export interface ScreenerStock {
  ticker: string
  name: string
  sector: string | null
  industry: string | null
  current_price: number | null
  market_cap: number | null
  // Valuation (undervalued signals)
  pe_ratio: number | null
  forward_pe: number | null
  peg_ratio: number | null
  pb_ratio: number | null
  // Growth signals
  revenue_growth: number | null
  eps_growth: number | null
  // Additional context
  profit_margin: number | null
  week_52_high: number | null
  week_52_low: number | null
}

export interface ScreenerResponse {
  results: ScreenerStock[]
  total: number
  industry: string
  min_price: number
  max_price: number
  /** Applied criteria — used to render the legend card. */
  criteria: ScreenerCriterion[]
  warnings: string[]
}
