/**
 * TypeScript interfaces for the Portfolio module.
 *
 * Every interface here mirrors a Pydantic model in
 * backend/app/schemas/portfolio.py, field-for-field.  Field names match the
 * Python snake_case names exactly so JSON responses from the API can be
 * assigned to these types without any runtime transformation.
 *
 * Nullability rule: every Python ``Optional[T]`` field (i.e. ``T | None``)
 * maps to ``T | null`` here.  Non-optional Python fields are required (no
 * ``?`` modifier, no ``| null``).
 *
 * Backend source of truth:
 *   backend/app/schemas/portfolio.py
 */

// ── Shared vocabulary ─────────────────────────────────────────────────────────

/**
 * What triggered a ranking snapshot to be written.
 * Mirrors the ``trigger`` column values in ``RankingSnapshot``.
 */
export type SnapshotTrigger = 'manual' | 'quarterly'

// ── Request / input shapes ────────────────────────────────────────────────────

/**
 * Request body for ``POST /api/portfolios``.
 * Mirrors: backend/app/schemas/portfolio.py :: PortfolioCreate
 */
export interface PortfolioCreate {
  /** Required. Human-readable portfolio name, 1–120 characters. */
  name: string
  /** Optional free-text description. Defaults to empty string when omitted. */
  description: string
}

/**
 * Request body for ``PATCH /api/portfolios/{id}``.
 * All fields are optional — only those present in the request body are applied.
 * Mirrors: backend/app/schemas/portfolio.py :: PortfolioUpdate
 */
export interface PortfolioUpdate {
  /**
   * New name to apply. ``null`` / absent means "leave unchanged".
   * When present, must be 1–120 characters.
   */
  name: string | null
  /**
   * New description to apply. ``null`` / absent means "leave unchanged".
   * An explicit empty string clears the description.
   */
  description: string | null
}

/**
 * Request body for ``POST /api/portfolios/{id}/stocks``.
 * Mirrors: backend/app/schemas/portfolio.py :: PortfolioStockIn
 */
export interface PortfolioStockIn {
  /**
   * Upper-case ticker symbol (e.g. ``"AAPL"``).
   * The backend normalises to upper-case, so mixed-case is accepted here too.
   */
  ticker: string
  /**
   * UUID string of a completed analysis report in the job store.
   * The backend rejects the request with HTTP 422 when the job is not complete.
   */
  job_id: string
}

// ── Response / output shapes ──────────────────────────────────────────────────

/**
 * A single stock entry as returned inside ``Portfolio.stocks`` and the
 * portfolio ranking table.
 * Mirrors: backend/app/schemas/portfolio.py :: PortfolioStockOut
 */
export interface PortfolioStock {
  /** Upper-case ticker symbol (e.g. ``"MSFT"``). */
  ticker: string
  /** Full company name (e.g. ``"Microsoft Corporation"``). */
  company_name: string
  /**
   * Executive summary from the most recent completed report.
   * Empty string until the first report is linked.
   */
  short_summary: string
  /**
   * Composite overall score (0–100) from the most recent report.
   * ``null`` when data could not be fetched or no report has been linked yet.
   */
  overall_score: number | null
  /**
   * Investment recommendation from the most recent report.
   * One of ``"Buy"``, ``"Hold"``, or ``"Sell"``; ``null`` until first report.
   */
  recommendation: string | null
  /**
   * Job ID of the most recently linked analysis report.
   * Points into the server's in-memory JobStore — becomes stale after a
   * server restart.  ``null`` until the first report is linked.
   */
  latest_report_id: string | null
  /** ISO 8601 UTC datetime string of when this stock was added to the portfolio. */
  added_at: string
  /**
   * ISO 8601 UTC datetime string of the most recent successful score update.
   * ``null`` until ``crud.update_stock_from_report()`` runs for this stock.
   */
  last_refreshed: string | null
}

/**
 * Full portfolio response returned by ``GET /api/portfolios/{id}``
 * and ``POST /api/portfolios``.
 * Mirrors: backend/app/schemas/portfolio.py :: PortfolioOut
 */
export interface Portfolio {
  /** UUID string that uniquely identifies this portfolio. */
  id: string
  /** Human-readable portfolio name. */
  name: string
  /** Free-text description; empty string when none was provided. */
  description: string
  /** ISO 8601 UTC datetime string of when the portfolio was created. */
  created_at: string
  /** ISO 8601 UTC datetime string of the most recent update to the portfolio row. */
  updated_at: string
  /**
   * All stocks currently in this portfolio.
   * Empty array when no stocks have been added yet.
   * Ordered by ``added_at`` ascending (insertion order) in the detail view.
   */
  stocks: PortfolioStock[]
}

/**
 * One ranked stock row returned by ``GET /api/portfolios/{id}/ranking``
 * and embedded in ``RankingSnapshot.entries``.
 * Mirrors: backend/app/schemas/portfolio.py :: RankingEntryOut
 */
export interface RankingEntry {
  /**
   * 1-based position in the ranking (rank 1 = highest ``overall_score``).
   * Equal scores are broken alphabetically by ticker.
   * Stocks with ``overall_score = null`` are placed at the bottom.
   */
  rank: number
  /** Upper-case ticker symbol. */
  ticker: string
  /**
   * Composite overall score (0–100).
   * ``null`` signals "⚠ Data unavailable" in the ranking table.
   */
  overall_score: number | null
  /** Fundamental analysis sub-score (0–100), or ``null`` if unavailable. */
  fundamental_score: number | null
  /** Technical analysis sub-score (0–100), or ``null`` if unavailable. */
  technical_score: number | null
  /** News sentiment sub-score (0–100), or ``null`` if unavailable. */
  sentiment_score: number | null
  /**
   * Investment recommendation at the time of this ranking.
   * One of ``"Buy"``, ``"Hold"``, ``"Sell"``; ``null`` when ``overall_score``
   * is ``null``.
   */
  recommendation: string | null
}

/**
 * A complete ranking snapshot returned by
 * ``GET /api/portfolios/{id}/history/{snapshot_id}``.
 *
 * The history list view (``GET /api/portfolios/{id}/history``) uses the same
 * shape but the server returns ``entries: []`` — entries are only populated
 * when a specific snapshot is fetched by ID.
 *
 * Mirrors: backend/app/schemas/portfolio.py :: RankingSnapshotOut
 */
export interface RankingSnapshot {
  /** UUID string that uniquely identifies this snapshot. */
  id: string
  /** ISO 8601 UTC datetime string of when this snapshot was written. */
  snapshot_at: string
  /**
   * What caused this snapshot to be written.
   * ``"manual"`` — user clicked "Refresh Now".
   * ``"quarterly"`` — APScheduler fired automatically.
   */
  trigger: SnapshotTrigger
  /**
   * Ranked stock entries for this snapshot, ordered ascending by ``rank``.
   * Empty array in the history list view; fully populated in the detail view.
   */
  entries: RankingEntry[]
}
