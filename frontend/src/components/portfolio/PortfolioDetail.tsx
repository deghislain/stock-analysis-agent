/**
 * PortfolioDetail — right-panel detail view for a selected portfolio.
 *
 * Shows the portfolio's metadata, a ranked stock table, and a "Refresh Now"
 * button.  The ``RankingHistory`` section is rendered below the table (added
 * in Todo 7).
 *
 * Props
 * ─────
 *   portfolioId — UUID of the selected portfolio.  The component is only
 *                 rendered when this is non-null (guarded by the parent page).
 *
 * Ranked stock table columns
 * ──────────────────────────
 *   Rank · Ticker · Company · Score · Recommendation · Last Refreshed · Actions
 *
 * "View" button
 * ─────────────
 *   Navigates to /report/{latest_report_id}.  The Report page already handles
 *   the case where the job no longer exists in the in-memory JobStore after a
 *   server restart — it renders its error state which (in Todo 10) will be
 *   extended with a "Report expired — regenerate" call-to-action.
 *   When latest_report_id is null (stock added but no report linked yet),
 *   the View button is replaced with a muted "—" placeholder.
 *
 * "Remove" button
 * ───────────────
 *   Shows window.confirm() then calls useRemoveStock(). Row goes semi-transparent
 *   while the mutation is pending to prevent double-removes.
 *
 * "Refresh Now" button
 * ────────────────────
 *   Calls useRefreshPortfolio(). Disabled + spinner while isPending.
 *   Returns 202 immediately; the new snapshot appears in the history section
 *   once the background task completes.
 *
 * Score display
 * ─────────────
 *   null overall_score → "⚠ N/A" in amber text (data unavailable).
 *   Non-null → rounded to one decimal place.
 *
 * Recommendation badge
 * ────────────────────
 *   Reuses the .badge-buy / .badge-hold / .badge-sell CSS classes from
 *   index.css.  null recommendation → muted dash.
 */

import { useNavigate } from 'react-router-dom'
import {
  usePortfolio,
  usePortfolioRanking,
  useRemoveStock,
  useRefreshPortfolio,
} from '../../hooks/usePortfolios'
import RankingHistory from './RankingHistory'
import type { RankingEntry } from '../../types/portfolio'

// ── Props ──────────────────────────────────────────────────────────────────────

interface PortfolioDetailProps {
  /** UUID of the portfolio to display. */
  portfolioId: string
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function PortfolioDetail({ portfolioId }: PortfolioDetailProps) {
  const navigate = useNavigate()

  const { data: portfolio, isLoading: portfolioLoading, error: portfolioError } =
    usePortfolio(portfolioId)

  const { data: ranking, isLoading: rankingLoading } =
    usePortfolioRanking(portfolioId)

  const removeMutation = useRemoveStock()
  const refreshMutation = useRefreshPortfolio()

  // ── Handlers ───────────────────────────────────────────────────────────────

  function handleRemove(ticker: string) {
    if (
      !window.confirm(
        `Remove ${ticker} from this portfolio?\n\nIts ranking history entries are preserved.`,
      )
    ) {
      return
    }
    removeMutation.mutate({ portfolioId, ticker })
  }

  function handleRefresh() {
    refreshMutation.mutate(portfolioId)
  }

  function handleView(reportId: string) {
    navigate(`/report/${reportId}`)
  }

  // ── Loading ─────────────────────────────────────────────────────────────────

  if (portfolioLoading) {
    return (
      <div className="flex flex-1 items-center justify-center p-12">
        <SpinnerIcon className="h-7 w-7 text-brand-500" />
      </div>
    )
  }

  // ── Error ──────────────────────────────────────────────────────────────────

  if (portfolioError || !portfolio) {
    return (
      <div className="flex flex-1 items-center justify-center p-12">
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600"
        >
          {portfolioError?.message ?? 'Portfolio not found.'}
        </div>
      </div>
    )
  }

  // ── Derived ────────────────────────────────────────────────────────────────

  // Build a ticker → PortfolioStock map so the ranking table can show
  // company name, last_refreshed, and latest_report_id alongside rank data.
  const stockMap = Object.fromEntries(portfolio.stocks.map((s) => [s.ticker, s]))

  // Use the live ranking when available; fall back to an unranked stock list
  // while the ranking query is loading so the table isn't blank.
  const rows: RankingEntry[] =
    ranking ??
    portfolio.stocks.map((s, i) => ({
      rank: i + 1,
      ticker: s.ticker,
      overall_score: s.overall_score,
      fundamental_score: null,
      technical_score: null,
      sentiment_score: null,
      recommendation: s.recommendation,
    }))

  const isRefreshing = refreshMutation.isPending

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto">

      {/* ── Portfolio header ───────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-xl font-semibold text-gray-900 truncate">
            {portfolio.name}
          </h2>
          {portfolio.description && (
            <p className="mt-0.5 text-sm text-gray-500 line-clamp-2">
              {portfolio.description}
            </p>
          )}
          <p className="mt-1 text-xs text-gray-400">
            {portfolio.stocks.length === 0
              ? 'No stocks yet'
              : `${portfolio.stocks.length} stock${portfolio.stocks.length === 1 ? '' : 's'}`}
            {' · '}Updated{' '}
            {new Date(portfolio.updated_at).toLocaleDateString(undefined, {
              year: 'numeric',
              month: 'short',
              day: 'numeric',
            })}
          </p>
        </div>

        {/* Refresh Now */}
        <button
          type="button"
          onClick={handleRefresh}
          disabled={isRefreshing || portfolio.stocks.length === 0}
          aria-label="Refresh all stocks in this portfolio"
          className={[
            'inline-flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium',
            'transition-colors',
            isRefreshing || portfolio.stocks.length === 0
              ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
              : 'bg-brand-600 text-white hover:bg-brand-700 cursor-pointer',
          ].join(' ')}
        >
          {isRefreshing ? <SpinnerIcon className="h-4 w-4" /> : <RefreshIcon />}
          {isRefreshing ? 'Refreshing…' : 'Refresh Now'}
        </button>
      </div>

      {/* Refresh success banner */}
      {refreshMutation.isSuccess && (
        <div
          role="status"
          className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700"
        >
          Refresh started — check the History section below for the new snapshot
          when it completes.
        </div>
      )}

      {/* Refresh error banner */}
      {refreshMutation.error && (
        <div
          role="alert"
          className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600"
        >
          Refresh failed: {(refreshMutation.error as Error).message}
        </div>
      )}

      {/* ── Ranked stock table ─────────────────────────────────────────────── */}
      <div className="card overflow-hidden p-0">
        <div className="border-b border-gray-200 px-4 py-3">
          <h3 className="text-sm font-semibold text-gray-700">
            Current Ranking
          </h3>
        </div>

        {/* Empty portfolio */}
        {portfolio.stocks.length === 0 && (
          <div className="px-4 py-8 text-center">
            <p className="text-sm text-gray-500">No stocks in this portfolio yet.</p>
            <p className="mt-1 text-xs text-gray-400">
              Run an analysis on any stock, then use the report page to add it here.
            </p>
          </div>
        )}

        {/* Table */}
        {portfolio.stocks.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="bg-gray-50 text-xs font-semibold uppercase tracking-wider text-gray-500">
                  <th className="px-4 py-2.5 text-center w-10">#</th>
                  <th className="px-4 py-2.5 text-left">Ticker</th>
                  <th className="px-4 py-2.5 text-left">Company</th>
                  <th className="px-4 py-2.5 text-right">Score</th>
                  <th className="px-4 py-2.5 text-center">Rec.</th>
                  <th className="px-4 py-2.5 text-left">Last Refreshed</th>
                  <th className="px-4 py-2.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {rankingLoading && rows.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-6 text-center text-gray-400 text-xs">
                      Loading ranking…
                    </td>
                  </tr>
                )}
                {rows.map((entry) => {
                  const stock = stockMap[entry.ticker]
                  const isRemoving =
                    removeMutation.isPending &&
                    removeMutation.variables?.ticker === entry.ticker &&
                    removeMutation.variables?.portfolioId === portfolioId

                  return (
                    <tr
                      key={entry.ticker}
                      className={[
                        'transition-opacity',
                        isRemoving ? 'opacity-40' : 'hover:bg-gray-50',
                      ].join(' ')}
                    >
                      {/* Rank */}
                      <td className="px-4 py-3 text-center font-mono text-xs text-gray-500">
                        {entry.rank}
                      </td>

                      {/* Ticker */}
                      <td className="px-4 py-3 font-mono font-semibold text-gray-900 whitespace-nowrap">
                        {entry.ticker}
                      </td>

                      {/* Company */}
                      <td className="px-4 py-3 text-gray-600 max-w-[180px] truncate">
                        {stock?.company_name || '—'}
                      </td>

                      {/* Score */}
                      <td className="px-4 py-3 text-right font-mono whitespace-nowrap">
                        {entry.overall_score == null ? (
                          <span className="text-amber-500 text-xs">⚠ N/A</span>
                        ) : (
                          <span className="text-gray-800">
                            {entry.overall_score.toFixed(1)}
                          </span>
                        )}
                      </td>

                      {/* Recommendation badge */}
                      <td className="px-4 py-3 text-center whitespace-nowrap">
                        <RecommendationBadge rec={entry.recommendation} />
                      </td>

                      {/* Last Refreshed */}
                      <td className="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">
                        {stock?.last_refreshed
                          ? new Date(stock.last_refreshed).toLocaleDateString(
                              undefined,
                              { year: 'numeric', month: 'short', day: 'numeric' },
                            )
                          : '—'}
                      </td>

                      {/* Actions: View + Remove */}
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <div className="inline-flex items-center gap-2">
                          {/* View — only enabled when a report ID is known */}
                          {stock?.latest_report_id ? (
                            <button
                              type="button"
                              onClick={() => handleView(stock.latest_report_id!)}
                              className="rounded px-2 py-1 text-xs font-medium text-brand-600 hover:bg-brand-50 transition-colors"
                            >
                              View
                            </button>
                          ) : (
                            <span className="px-2 py-1 text-xs text-gray-300">—</span>
                          )}

                          {/* Remove */}
                          <button
                            type="button"
                            onClick={() => handleRemove(entry.ticker)}
                            disabled={isRemoving}
                            aria-label={`Remove ${entry.ticker}`}
                            className="rounded px-2 py-1 text-xs font-medium text-red-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                          >
                            Remove
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Ranking history (Todo 7) ───────────────────────────────────────── */}
      <RankingHistory portfolioId={portfolioId} />

    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

/** Renders a Buy / Hold / Sell badge using the shared CSS classes from index.css. */
function RecommendationBadge({ rec }: { rec: string | null }) {
  if (!rec) return <span className="text-gray-300 text-xs">—</span>
  const cls =
    rec === 'Buy' ? 'badge-buy' : rec === 'Sell' ? 'badge-sell' : 'badge-hold'
  return <span className={cls}>{rec}</span>
}

// ── Icons ──────────────────────────────────────────────────────────────────────

function SpinnerIcon({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className}`}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  )
}

function RefreshIcon() {
  return (
    <svg
      className="h-4 w-4"
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H3.989a.75.75 0 00-.75.75v4.242a.75.75 0 001.5 0v-2.43l.31.31a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm1.23-3.723a.75.75 0 00.219-.53V2.929a.75.75 0 00-1.5 0V5.36l-.31-.31A7 7 0 003.239 8.188a.75.75 0 101.448.389A5.5 5.5 0 0113.89 6.11l.311.31h-2.432a.75.75 0 000 1.5h4.243a.75.75 0 00.53-.219z"
        clipRule="evenodd"
      />
    </svg>
  )
}
