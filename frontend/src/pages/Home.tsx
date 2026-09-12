/**
 * Home — landing page for the Stock Analysis Agent.
 *
 * Layout
 * ──────
 *   Vertically and horizontally centred card:
 *     • App title and subtitle with mandatory disclaimer text
 *     • TickerInput — calls validateTicker on blur/Enter, shows inline state
 *     • "Generate Report" button — disabled until a valid ticker is confirmed
 *
 * Flow
 * ────
 *   1. User types a ticker, TickerInput validates it via GET /api/validate/{ticker}.
 *   2. On success the TickerInput calls `onSubmit(ticker)`, which fires the
 *      `useAnalysis().start()` mutation (POST /api/analyse).
 *   3. As soon as `jobId` is returned from the mutation, a `useEffect` navigates
 *      to /report/:jobId — the Report page then owns the polling lifecycle.
 */

import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import TickerInput from '../components/TickerInput'
import { useAnalysis } from '../hooks/useAnalysis'

// ── Component ─────────────────────────────────────────────────────────────────

export default function Home() {
  const navigate = useNavigate()
  const { start, jobId, isSubmitting } = useAnalysis()

  // Navigate to the report page as soon as the mutation returns a jobId.
  useEffect(() => {
    if (jobId) {
      navigate(`/report/${jobId}`)
    }
  }, [jobId, navigate])

  /**
   * Called by TickerInput when the user submits a validated ticker.
   * Fires the POST /api/analyse mutation; the useEffect above handles navigation.
   */
  function handleSubmit(ticker: string): void {
    start(ticker)
  }

  return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md space-y-4">

        {/* ── Hero + input — single cohesive card ──────────────────────── */}
        <div className="card space-y-6">

          {/* Title block */}
          <div className="text-center space-y-2">
            <h1 className="text-3xl font-bold tracking-tight text-gray-900">
              Stock Analysis Agent
            </h1>
            <p className="text-sm text-gray-500 leading-relaxed">
              Enter a stock ticker to receive an AI-powered fundamental,
              technical, and sentiment report.
            </p>
            {/* Mandatory disclaimer — hero subtitle (plan requirement) */}
            <p className="disclaimer">
              For informational purposes only. Not financial advice.
            </p>
          </div>

          {/* Divider */}
          <hr className="border-gray-100" />

          {/* Ticker input */}
          <TickerInput onSubmit={handleSubmit} disabled={isSubmitting} />

          {/* Submitting feedback */}
          {isSubmitting && (
            <p className="text-center text-sm text-gray-500 animate-pulse">
              Starting analysis…
            </p>
          )}
        </div>

        {/* ── Timing hint ──────────────────────────────────────────────── */}
        <p className="text-center disclaimer">
          Analysis typically takes 20–40 seconds.
        </p>

      </div>
    </main>
  )
}
