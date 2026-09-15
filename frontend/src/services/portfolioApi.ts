/**
 * Axios API client for the Portfolio module endpoints.
 *
 * One function is exported per backend endpoint.  All functions are typed with
 * the interfaces from ``src/types/portfolio.ts`` which mirror
 * ``backend/app/schemas/portfolio.py`` field-for-field.
 *
 * Endpoint map
 * ────────────
 *   listPortfolios()                          GET  /api/portfolios
 *   createPortfolio(body)                     POST /api/portfolios
 *   getPortfolio(id)                          GET  /api/portfolios/{id}
 *   updatePortfolio(id, body)                 PATCH /api/portfolios/{id}
 *   deletePortfolio(id)                       DELETE /api/portfolios/{id}
 *   addStock(portfolioId, body)               POST /api/portfolios/{id}/stocks
 *   removeStock(portfolioId, ticker)          DELETE /api/portfolios/{id}/stocks/{ticker}
 *   getPortfolioRanking(portfolioId)          GET  /api/portfolios/{id}/ranking
 *   refreshPortfolio(portfolioId)             POST /api/portfolios/{id}/refresh
 *   getRankingHistory(portfolioId)            GET  /api/portfolios/{id}/history
 *   getRankingSnapshot(portfolioId, snapId)   GET  /api/portfolios/{id}/history/{snapshot_id}
 *
 * Error handling
 * ──────────────
 * The shared ``portfolioClient`` Axios instance re-uses the same interceptor
 * pattern as ``services/api.ts``: 4xx responses are converted to plain
 * ``Error`` objects with the FastAPI ``detail`` string as the message.  5xx
 * and network errors propagate unchanged.  TanStack Query mutations and queries
 * surface these errors via their ``error`` state — nothing is swallowed here.
 *
 * Base URL
 * ────────
 * ``baseURL`` is intentionally empty.  In development, Vite proxies ``/api/*``
 * to ``http://localhost:8000``; in production, nginx handles the same routing.
 */

import axios, { type AxiosError } from 'axios'
import type {
  Portfolio,
  PortfolioCreate,
  PortfolioUpdate,
  PortfolioStock,
  PortfolioStockIn,
  RankingEntry,
  RankingSnapshot,
} from '../types/portfolio'

// ── Shared Axios instance ──────────────────────────────────────────────────────

/**
 * Dedicated Axios instance for portfolio endpoints.
 *
 * Kept separate from the analysis ``client`` in ``services/api.ts`` so the two
 * concerns can evolve independently (e.g. different base URLs in the future).
 */
const portfolioClient = axios.create({
  baseURL: '',
  headers: { 'Content-Type': 'application/json' },
  // Let 4xx through so the interceptor below can extract the detail string.
  validateStatus: (status) => status < 500,
})

/**
 * Response interceptor — converts FastAPI ``{ detail: string }`` error shapes
 * into plain ``Error`` objects so TanStack Query mutation/query ``error`` state
 * always holds a consistent, human-readable message.
 */
portfolioClient.interceptors.response.use(
  (response) => {
    if (response.status >= 400) {
      const detail = (response.data as { detail?: string })?.detail
      const message =
        typeof detail === 'string'
          ? detail
          : `Request failed with status ${response.status}`
      return Promise.reject(new Error(message))
    }
    return response
  },
  (error: AxiosError) => {
    const message =
      error.message ?? 'Network error — could not reach the backend.'
    return Promise.reject(new Error(message))
  },
)

// ── Helpers ────────────────────────────────────────────────────────────────────

/** Encode a portfolio ID safely for use in URL path segments. */
const pid = (id: string) => encodeURIComponent(id)

// ── Portfolio CRUD ─────────────────────────────────────────────────────────────

/**
 * Return all portfolios ordered by creation date (oldest first).
 *
 * Calls ``GET /api/portfolios``.
 *
 * @returns Array of ``Portfolio`` objects, each with its ``stocks`` list.
 */
export async function listPortfolios(): Promise<Portfolio[]> {
  const { data } = await portfolioClient.get<Portfolio[]>('/api/portfolios')
  return data
}

/**
 * Create a new named portfolio.
 *
 * Calls ``POST /api/portfolios`` → HTTP 201.
 *
 * @param body  ``name`` (required, 1–120 chars) and optional ``description``.
 * @returns The newly created ``Portfolio``.
 */
export async function createPortfolio(body: PortfolioCreate): Promise<Portfolio> {
  const { data } = await portfolioClient.post<Portfolio>('/api/portfolios', body)
  return data
}

/**
 * Fetch a single portfolio with its full stock list.
 *
 * Calls ``GET /api/portfolios/{id}`` → 200 or 404.
 *
 * @param id  UUID string of the portfolio.
 * @returns The matching ``Portfolio`` with its ``stocks`` populated.
 */
export async function getPortfolio(id: string): Promise<Portfolio> {
  const { data } = await portfolioClient.get<Portfolio>(`/api/portfolios/${pid(id)}`)
  return data
}

/**
 * Partially update a portfolio's name and/or description.
 *
 * Calls ``PATCH /api/portfolios/{id}`` → 200 or 404.
 * Fields absent from ``body`` (i.e. ``null``) are left unchanged.
 *
 * @param id    UUID string of the portfolio to update.
 * @param body  Partial update — include only the fields to change.
 * @returns The updated ``Portfolio``.
 */
export async function updatePortfolio(
  id: string,
  body: PortfolioUpdate,
): Promise<Portfolio> {
  const { data } = await portfolioClient.patch<Portfolio>(
    `/api/portfolios/${pid(id)}`,
    body,
  )
  return data
}

/**
 * Delete a portfolio and all its stocks and ranking snapshots.
 *
 * Calls ``DELETE /api/portfolios/{id}`` → 204 or 404.
 *
 * @param id  UUID string of the portfolio to delete.
 * @returns void (HTTP 204 has no body).
 */
export async function deletePortfolio(id: string): Promise<void> {
  await portfolioClient.delete(`/api/portfolios/${pid(id)}`)
}

// ── Stock management ───────────────────────────────────────────────────────────

/**
 * Add a stock to a portfolio using data from a completed analysis report.
 *
 * Calls ``POST /api/portfolios/{portfolioId}/stocks`` → 201, 404, 409, or 422.
 *
 * Possible error cases (propagated as ``Error`` by the interceptor):
 *   - 404 — portfolio not found.
 *   - 409 — ticker already in this portfolio.
 *   - 422 — referenced job is not complete or ticker format is invalid.
 *
 * @param portfolioId  UUID string of the target portfolio.
 * @param body         ``ticker`` and ``job_id`` of the completed report.
 * @returns The newly created ``PortfolioStock`` row.
 */
export async function addStock(
  portfolioId: string,
  body: PortfolioStockIn,
): Promise<PortfolioStock> {
  const { data } = await portfolioClient.post<PortfolioStock>(
    `/api/portfolios/${pid(portfolioId)}/stocks`,
    body,
  )
  return data
}

/**
 * Remove a stock from a portfolio.
 *
 * Calls ``DELETE /api/portfolios/{portfolioId}/stocks/{ticker}`` → 204 or 404.
 *
 * @param portfolioId  UUID string of the owning portfolio.
 * @param ticker       Upper-case ticker symbol to remove.
 * @returns void (HTTP 204 has no body).
 */
export async function removeStock(
  portfolioId: string,
  ticker: string,
): Promise<void> {
  await portfolioClient.delete(
    `/api/portfolios/${pid(portfolioId)}/stocks/${encodeURIComponent(ticker)}`,
  )
}

// ── Ranking ────────────────────────────────────────────────────────────────────

/**
 * Return the current live ranking of all stocks in a portfolio.
 *
 * Calls ``GET /api/portfolios/{portfolioId}/ranking`` → 200 or 404.
 *
 * Stocks are ordered by ``overall_score`` descending (rank 1 = best score).
 * Equal scores are broken alphabetically by ticker.
 * Stocks with no score appear at the bottom with ``overall_score: null``.
 *
 * @param portfolioId  UUID string of the portfolio.
 * @returns Ordered array of ``RankingEntry`` objects.
 */
export async function getPortfolioRanking(
  portfolioId: string,
): Promise<RankingEntry[]> {
  const { data } = await portfolioClient.get<RankingEntry[]>(
    `/api/portfolios/${pid(portfolioId)}/ranking`,
  )
  return data
}

// ── Refresh ────────────────────────────────────────────────────────────────────

/**
 * Trigger a manual re-analysis of every stock in the portfolio.
 *
 * Calls ``POST /api/portfolios/{portfolioId}/refresh`` → 202 or 404.
 *
 * Returns immediately (HTTP 202).  The heavy work runs in a background task.
 * Poll ``getRankingHistory`` to detect when the new snapshot appears.
 *
 * @param portfolioId  UUID string of the portfolio to refresh.
 * @returns The ``{ detail: string }`` acknowledgement message.
 */
export async function refreshPortfolio(
  portfolioId: string,
): Promise<{ detail: string }> {
  const { data } = await portfolioClient.post<{ detail: string }>(
    `/api/portfolios/${pid(portfolioId)}/refresh`,
  )
  return data
}

// ── Ranking history ────────────────────────────────────────────────────────────

/**
 * List all ranking snapshots for a portfolio, newest first.
 *
 * Calls ``GET /api/portfolios/{portfolioId}/history`` → 200 or 404.
 *
 * The server returns snapshots with ``entries: []`` in this list view —
 * entries are only populated when a specific snapshot is fetched by ID
 * via ``getRankingSnapshot``.
 *
 * @param portfolioId  UUID string of the portfolio.
 * @returns Array of ``RankingSnapshot`` objects (without entries).
 */
export async function getRankingHistory(
  portfolioId: string,
): Promise<RankingSnapshot[]> {
  const { data } = await portfolioClient.get<RankingSnapshot[]>(
    `/api/portfolios/${pid(portfolioId)}/history`,
  )
  return data
}

/**
 * Fetch a single ranking snapshot with its full list of ranked entries.
 *
 * Calls ``GET /api/portfolios/{portfolioId}/history/{snapshotId}`` → 200 or 404.
 *
 * Use this for the expanded detail view of a snapshot row in
 * ``RankingHistory.tsx`` — it lazy-loads the entries only when the user
 * expands a row.
 *
 * @param portfolioId  UUID string of the owning portfolio.
 * @param snapshotId   UUID string of the snapshot to retrieve.
 * @returns The full ``RankingSnapshot`` with ``entries`` populated.
 */
export async function getRankingSnapshot(
  portfolioId: string,
  snapshotId: string,
): Promise<RankingSnapshot> {
  const { data } = await portfolioClient.get<RankingSnapshot>(
    `/api/portfolios/${pid(portfolioId)}/history/${encodeURIComponent(snapshotId)}`,
  )
  return data
}
