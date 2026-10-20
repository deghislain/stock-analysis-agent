/**
 * WatchlistPage — side-by-side comparison of candidate stocks.
 *
 * Shows all watchlist entries sorted by overall_score descending.
 * Each row links to its latest analysis report.  The user can add or
 * remove tickers directly from this page.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  getWatchlist,
  addToWatchlist,
  removeFromWatchlist,
} from '../services/api'

// ── Helpers ───────────────────────────────────────────────────────────────────

function recommendationColour(rec: string | null): string {
  if (rec === 'Buy')  return 'bg-green-50 text-green-700'
  if (rec === 'Sell') return 'bg-red-50 text-red-700'
  if (rec === 'Hold') return 'bg-yellow-50 text-yellow-700'
  return 'bg-gray-50 text-gray-500'
}

function scoreColour(score: number | null): string {
  if (score === null) return 'text-gray-400'
  if (score >= 60) return 'text-green-600'
  if (score >= 40) return 'text-yellow-600'
  return 'text-red-500'
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function WatchlistPage() {
  const queryClient = useQueryClient()
  const [tickerInput, setTickerInput] = useState('')
  const [addError, setAddError] = useState<string | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ['watchlist'],
    queryFn: getWatchlist,
    refetchInterval: 10_000,  // refresh every 10 s in case background jobs complete
  })

  const addMutation = useMutation({
    mutationFn: (ticker: string) => addToWatchlist(ticker),
    onSuccess: () => {
      setTickerInput('')
      setAddError(null)
      queryClient.invalidateQueries({ queryKey: ['watchlist'] })
    },
    onError: (err: Error) => {
      setAddError(err.message)
    },
  })

  const removeMutation = useMutation({
    mutationFn: (ticker: string) => removeFromWatchlist(ticker),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] })
    },
  })

  function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    const t = tickerInput.trim().toUpperCase()
    if (!t) return
    setAddError(null)
    addMutation.mutate(t)
  }

  return (
    <div className="min-h-screen bg-gray-50">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 bg-white border-b border-gray-200 shadow-sm">
        <div className="mx-auto max-w-3xl flex items-center justify-between px-4 py-3">
          <h1 className="text-lg font-bold text-gray-900">Watchlist</h1>
          <Link
            to="/"
            className="rounded-md px-3 py-1.5 text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50 transition-colors"
          >
            ← New analysis
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-6 px-4 py-8">

        {/* ── Add ticker form ───────────────────────────────────────────────── */}
        <section className="card">
          <h2 className="section-heading">Add to Watchlist</h2>
          <form onSubmit={handleAdd} className="flex gap-2">
            <input
              type="text"
              value={tickerInput}
              onChange={e => setTickerInput(e.target.value.toUpperCase())}
              placeholder="e.g. AAPL"
              className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm font-mono uppercase focus:outline-none focus:ring-2 focus:ring-brand-400"
              maxLength={7}
              aria-label="Ticker symbol"
            />
            <button
              type="submit"
              disabled={addMutation.isPending}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {addMutation.isPending ? 'Adding…' : 'Add'}
            </button>
          </form>
          {addError && (
            <p className="mt-2 text-xs text-red-600">{addError}</p>
          )}
          <p className="mt-2 text-xs text-gray-400">
            Adding a ticker triggers a background analysis. Scores update when the job completes.
          </p>
        </section>

        {/* ── Watchlist table ───────────────────────────────────────────────── */}
        <section className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="section-heading mb-0">
              Candidates
              {data && (
                <span className="ml-2 text-xs font-normal text-gray-400">({data.total})</span>
              )}
            </h2>
          </div>

          {isLoading && (
            <p className="text-sm text-gray-500">Loading watchlist…</p>
          )}

          {error && (
            <p className="text-sm text-red-600">Failed to load watchlist: {error.message}</p>
          )}

          {data && data.entries.length === 0 && (
            <p className="text-sm text-gray-500">
              Your watchlist is empty. Add a ticker above to start comparing candidates.
            </p>
          )}

          {data && data.entries.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
                    <th className="pb-2 pr-4">Ticker</th>
                    <th className="pb-2 pr-4">Score</th>
                    <th className="pb-2 pr-4">Signal</th>
                    <th className="pb-2 pr-4">Last Analysed</th>
                    <th className="pb-2"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {data.entries.map(entry => (
                    <tr key={entry.ticker} className="align-middle">

                      {/* Ticker */}
                      <td className="py-3 pr-4 font-mono font-bold text-gray-900 whitespace-nowrap">
                        {entry.latest_job_id ? (
                          <Link
                            to={`/report/${entry.latest_job_id}`}
                            className="text-brand-600 hover:underline"
                          >
                            {entry.ticker}
                          </Link>
                        ) : (
                          entry.ticker
                        )}
                      </td>

                      {/* Score */}
                      <td className={`py-3 pr-4 tabular-nums font-semibold ${scoreColour(entry.overall_score)}`}>
                        {entry.overall_score != null ? entry.overall_score.toFixed(1) : '—'}
                      </td>

                      {/* Recommendation */}
                      <td className="py-3 pr-4">
                        {entry.recommendation ? (
                          <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${recommendationColour(entry.recommendation)}`}>
                            {entry.recommendation}
                          </span>
                        ) : (
                          <span className="text-gray-400 text-xs">Pending</span>
                        )}
                      </td>

                      {/* Last analysed */}
                      <td className="py-3 pr-4 text-gray-500 text-xs whitespace-nowrap">
                        {entry.last_analysed_at
                          ? new Date(entry.last_analysed_at).toLocaleDateString()
                          : '—'}
                      </td>

                      {/* Remove */}
                      <td className="py-3 text-right">
                        <button
                          type="button"
                          onClick={() => removeMutation.mutate(entry.ticker)}
                          disabled={removeMutation.isPending}
                          className="text-xs text-gray-400 hover:text-red-500 transition-colors"
                          aria-label={`Remove ${entry.ticker} from watchlist`}
                        >
                          ✕
                        </button>
                      </td>

                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* ── Disclaimer ────────────────────────────────────────────────────── */}
        <p className="disclaimer text-center">
          For informational purposes only. Not financial advice.
        </p>

      </main>
    </div>
  )
}
