/**
 * TanStack Query hooks for the Portfolio module (Sub-Task P5, Todo 3).
 *
 * Every hook maps 1-to-1 to an endpoint function in ``services/portfolioApi.ts``.
 * Query keys follow a two-level hierarchy so invalidations are surgical:
 *
 *   ["portfolios"]                            — the full list
 *   ["portfolio", id]                         — one portfolio + its stocks
 *   ["portfolioRanking", id]                  — live ranking for one portfolio
 *   ["rankingHistory", id]                    — snapshot list for one portfolio
 *   ["rankingSnapshot", portfolioId, snapId]  — one snapshot with full entries
 *
 * Invalidation rules (applied by every mutation that changes portfolio state):
 *   - Add / remove stock, rename, delete  →  invalidate ["portfolios"] + ["portfolio", id]
 *   - Refresh                             →  same + ["portfolioRanking", id] + ["rankingHistory", id]
 *   - Create portfolio                    →  invalidate ["portfolios"] only
 *   - Delete portfolio                    →  invalidate ["portfolios"] + remove ["portfolio", id]
 *
 * Hooks exported
 * ──────────────
 *   usePortfolios()                         — list all portfolios
 *   usePortfolio(id)                        — one portfolio + stocks
 *   useCreatePortfolio()                    — mutation: POST /api/portfolios
 *   useUpdatePortfolio()                    — mutation: PATCH /api/portfolios/{id}
 *   useDeletePortfolio()                    — mutation: DELETE /api/portfolios/{id}
 *   useAddStock()                           — mutation: POST /api/portfolios/{id}/stocks
 *   useRemoveStock()                        — mutation: DELETE /api/portfolios/{id}/stocks/{ticker}
 *   usePortfolioRanking(id)                 — live ranking query
 *   useRefreshPortfolio()                   — mutation: POST /api/portfolios/{id}/refresh
 *   useRankingHistory(id)                   — snapshot list query
 *   useRankingSnapshot(portfolioId, snapId) — single snapshot with entries (lazy)
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  listPortfolios,
  createPortfolio,
  getPortfolio,
  updatePortfolio,
  deletePortfolio,
  addStock,
  removeStock,
  getPortfolioRanking,
  refreshPortfolio,
  getRankingHistory,
  getRankingSnapshot,
} from '../services/portfolioApi'
import type {
  Portfolio,
  PortfolioCreate,
  PortfolioUpdate,
  PortfolioStock,
  PortfolioStockIn,
  RankingEntry,
  RankingSnapshot,
} from '../types/portfolio'

// ── Query: list all portfolios ─────────────────────────────────────────────────

/**
 * Fetch all portfolios ordered by creation date (oldest first).
 *
 * Calls ``GET /api/portfolios``.
 *
 * @returns TanStack Query result with ``data: Portfolio[]``.
 */
export function usePortfolios() {
  return useQuery<Portfolio[], Error>({
    queryKey: ['portfolios'],
    queryFn: listPortfolios,
  })
}

// ── Query: single portfolio ────────────────────────────────────────────────────

/**
 * Fetch one portfolio with its full stock list.
 *
 * Calls ``GET /api/portfolios/{id}``.
 * The query is disabled when ``id`` is falsy (e.g. no portfolio selected yet).
 *
 * @param id  UUID string of the portfolio, or ``null`` / ``undefined`` when idle.
 * @returns TanStack Query result with ``data: Portfolio``.
 */
export function usePortfolio(id: string | null | undefined) {
  return useQuery<Portfolio, Error>({
    queryKey: ['portfolio', id],
    queryFn: () => getPortfolio(id!),
    enabled: Boolean(id),
  })
}

// ── Mutation: create portfolio ─────────────────────────────────────────────────

/**
 * Create a new portfolio.
 *
 * Calls ``POST /api/portfolios`` → HTTP 201.
 * On success, invalidates ``["portfolios"]`` so the list re-fetches.
 *
 * @example
 *   const { mutate } = useCreatePortfolio()
 *   mutate({ name: 'Tech Picks', description: '' })
 */
export function useCreatePortfolio() {
  const queryClient = useQueryClient()

  return useMutation<Portfolio, Error, PortfolioCreate>({
    mutationFn: createPortfolio,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portfolios'] })
    },
  })
}

// ── Mutation: update portfolio ─────────────────────────────────────────────────

/**
 * Partially update a portfolio's name and/or description.
 *
 * Calls ``PATCH /api/portfolios/{id}``.
 * On success, invalidates both ``["portfolios"]`` and ``["portfolio", id]``.
 *
 * @example
 *   const { mutate } = useUpdatePortfolio()
 *   mutate({ id: 'abc-123', body: { name: 'New Name', description: null } })
 */
export function useUpdatePortfolio() {
  const queryClient = useQueryClient()

  return useMutation<Portfolio, Error, { id: string; body: PortfolioUpdate }>({
    mutationFn: ({ id, body }) => updatePortfolio(id, body),
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['portfolios'] })
      queryClient.invalidateQueries({ queryKey: ['portfolio', id] })
    },
  })
}

// ── Mutation: delete portfolio ─────────────────────────────────────────────────

/**
 * Delete a portfolio and all its child rows.
 *
 * Calls ``DELETE /api/portfolios/{id}`` → HTTP 204.
 * On success, invalidates ``["portfolios"]`` and removes the ``["portfolio", id]``
 * cache entry so a stale detail panel cannot be shown.
 *
 * @example
 *   const { mutate } = useDeletePortfolio()
 *   mutate('abc-123')
 */
export function useDeletePortfolio() {
  const queryClient = useQueryClient()

  return useMutation<void, Error, string>({
    mutationFn: deletePortfolio,
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ['portfolios'] })
      queryClient.removeQueries({ queryKey: ['portfolio', id] })
    },
  })
}

// ── Mutation: add stock ────────────────────────────────────────────────────────

/**
 * Add a stock to a portfolio using a completed analysis report.
 *
 * Calls ``POST /api/portfolios/{portfolioId}/stocks`` → HTTP 201.
 * On success, invalidates ``["portfolios"]`` and ``["portfolio", portfolioId]``.
 *
 * Possible error messages (from the interceptor):
 *   - 409 — ticker already in portfolio.
 *   - 422 — job not complete, or invalid ticker format.
 *
 * @example
 *   const { mutate } = useAddStock()
 *   mutate({ portfolioId: 'abc-123', body: { ticker: 'AAPL', job_id: 'job-456' } })
 */
export function useAddStock() {
  const queryClient = useQueryClient()

  return useMutation<
    PortfolioStock,
    Error,
    { portfolioId: string; body: PortfolioStockIn }
  >({
    mutationFn: ({ portfolioId, body }) => addStock(portfolioId, body),
    onSuccess: (_data, { portfolioId }) => {
      queryClient.invalidateQueries({ queryKey: ['portfolios'] })
      queryClient.invalidateQueries({ queryKey: ['portfolio', portfolioId] })
    },
  })
}

// ── Mutation: remove stock ─────────────────────────────────────────────────────

/**
 * Remove a stock from a portfolio.
 *
 * Calls ``DELETE /api/portfolios/{portfolioId}/stocks/{ticker}`` → HTTP 204.
 * On success, invalidates ``["portfolios"]`` and ``["portfolio", portfolioId]``.
 *
 * @example
 *   const { mutate } = useRemoveStock()
 *   mutate({ portfolioId: 'abc-123', ticker: 'AAPL' })
 */
export function useRemoveStock() {
  const queryClient = useQueryClient()

  return useMutation<void, Error, { portfolioId: string; ticker: string }>({
    mutationFn: ({ portfolioId, ticker }) => removeStock(portfolioId, ticker),
    onSuccess: (_data, { portfolioId }) => {
      queryClient.invalidateQueries({ queryKey: ['portfolios'] })
      queryClient.invalidateQueries({ queryKey: ['portfolio', portfolioId] })
    },
  })
}

// ── Query: live portfolio ranking ──────────────────────────────────────────────

/**
 * Fetch the current live ranking of all stocks in a portfolio.
 *
 * Calls ``GET /api/portfolios/{id}/ranking``.
 * Disabled when ``id`` is falsy.
 *
 * Stocks are ordered by ``overall_score`` descending (rank 1 = best).
 * Stocks with ``overall_score: null`` appear at the bottom.
 *
 * @param id  UUID string of the portfolio, or ``null`` / ``undefined`` when idle.
 * @returns TanStack Query result with ``data: RankingEntry[]``.
 */
export function usePortfolioRanking(id: string | null | undefined) {
  return useQuery<RankingEntry[], Error>({
    queryKey: ['portfolioRanking', id],
    queryFn: () => getPortfolioRanking(id!),
    enabled: Boolean(id),
  })
}

// ── Mutation: manual refresh ───────────────────────────────────────────────────

/**
 * Trigger a manual re-analysis of every stock in a portfolio.
 *
 * Calls ``POST /api/portfolios/{portfolioId}/refresh`` → HTTP 202.
 * Returns immediately; the analysis runs in the background.
 *
 * On success, invalidates:
 *   - ``["portfolios"]``
 *   - ``["portfolio", portfolioId]``
 *   - ``["portfolioRanking", portfolioId]``
 *   - ``["rankingHistory", portfolioId]``
 *
 * The component should disable the "Refresh Now" button while
 * ``mutation.isPending`` is ``true`` and poll / re-enable when it settles.
 *
 * @example
 *   const { mutate, isPending } = useRefreshPortfolio()
 *   mutate('abc-123')
 */
export function useRefreshPortfolio() {
  const queryClient = useQueryClient()

  return useMutation<{ detail: string }, Error, string>({
    mutationFn: refreshPortfolio,
    onSuccess: (_data, portfolioId) => {
      queryClient.invalidateQueries({ queryKey: ['portfolios'] })
      queryClient.invalidateQueries({ queryKey: ['portfolio', portfolioId] })
      queryClient.invalidateQueries({ queryKey: ['portfolioRanking', portfolioId] })
      queryClient.invalidateQueries({ queryKey: ['rankingHistory', portfolioId] })
    },
  })
}

// ── Query: ranking history list ────────────────────────────────────────────────

/**
 * Fetch all ranking snapshots for a portfolio, newest first.
 *
 * Calls ``GET /api/portfolios/{id}/history``.
 * Snapshots are returned with ``entries: []`` — use ``useRankingSnapshot`` to
 * lazy-load the full entry list when a row is expanded.
 * Disabled when ``id`` is falsy.
 *
 * @param id  UUID string of the portfolio, or ``null`` / ``undefined`` when idle.
 * @returns TanStack Query result with ``data: RankingSnapshot[]`` (entries empty).
 */
export function useRankingHistory(id: string | null | undefined) {
  return useQuery<RankingSnapshot[], Error>({
    queryKey: ['rankingHistory', id],
    queryFn: () => getRankingHistory(id!),
    enabled: Boolean(id),
  })
}

// ── Query: single snapshot with entries ───────────────────────────────────────

/**
 * Fetch a single ranking snapshot with its full ``entries`` list.
 *
 * Calls ``GET /api/portfolios/{portfolioId}/history/{snapshotId}``.
 * Only fires when both ``portfolioId`` and ``snapshotId`` are non-falsy —
 * designed for lazy loading when the user expands a row in ``RankingHistory``.
 *
 * @param portfolioId  UUID string of the owning portfolio.
 * @param snapshotId   UUID string of the snapshot to load, or ``null`` when collapsed.
 * @returns TanStack Query result with ``data: RankingSnapshot`` (entries populated).
 */
export function useRankingSnapshot(
  portfolioId: string | null | undefined,
  snapshotId: string | null | undefined,
) {
  return useQuery<RankingSnapshot, Error>({
    queryKey: ['rankingSnapshot', portfolioId, snapshotId],
    queryFn: () => getRankingSnapshot(portfolioId!, snapshotId!),
    enabled: Boolean(portfolioId) && Boolean(snapshotId),
  })
}
