/**
 * Report — full analysis dashboard shown after a job completes.
 *
 * This page owns the polling lifecycle for the given jobId (taken from the
 * URL parameter). The hook polls every 2 seconds and this page renders the
 * correct UI for each phase:
 *
 *   • pending / running  → LoadingSpinner with live step label
 *   • complete           → full dashboard (ExecutiveSummary, panels, charts)
 *   • error              → error card with a "Try again" link back to Home
 *
 * Dashboard layout (top to bottom, when complete)
 * ─────────────────────────────────────────────────
 *   1. Header bar — ticker + "Back" link
 *   2. DataSourcesBadge + WarningFlags
 *   3. ExecutiveSummary
 *   4. FundamentalPanel
 *   5. TechnicalPanel
 *   6. NewsPanel
 *   7. PDF download row + disclaimer (plan requirement)
 */

import { useParams, Link, useNavigate } from 'react-router-dom'
import { useAnalysis } from '../hooks/useAnalysis'
import LoadingSpinner from '../components/LoadingSpinner'
import ExecutiveSummary from '../components/ExecutiveSummary'
import FundamentalPanel from '../components/FundamentalPanel'
import TechnicalPanel from '../components/TechnicalPanel'
import NewsPanel from '../components/NewsPanel'
import DataSourcesBadge from '../components/DataSourcesBadge'
import WarningFlags from '../components/WarningFlags'
import { getPdfUrl } from '../services/api'

// ── Component ─────────────────────────────────────────────────────────────────

export default function Report() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()

  // Pass jobId from the URL directly into useAnalysis so polling starts
  // immediately when this page mounts — even though the mutation that created
  // the job ran inside the Home page's hook instance, not this one.
  const { status, currentStep, report, error, isLoading } = useAnalysis(jobId)

  // Guard: jobId is guaranteed by React Router's <Route path="/report/:jobId">
  // so this branch only fires on a malformed direct URL with no param.
  if (!jobId) {
    navigate('/', { replace: true })
    return null
  }

  // ── Loading state ──────────────────────────────────────────────────────────

  if (isLoading || status === 'pending' || status === 'running') {
    return (
      <main className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-6 gap-6">
        <LoadingSpinner currentStep={currentStep} ticker={report?.ticker} />
      </main>
    )
  }

  // ── Error state ────────────────────────────────────────────────────────────

  if (status === 'error' || error) {
    return (
      <main className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
        <div className="card w-full max-w-md space-y-4 text-center">
          <h2 className="text-lg font-semibold text-red-600">Analysis failed</h2>
          <p className="text-sm text-gray-600">
            {error ?? 'An unexpected error occurred. Please try again.'}
          </p>
          <Link
            to="/"
            className="inline-block rounded-lg bg-brand-600 px-5 py-2 text-sm font-semibold text-white hover:bg-brand-700"
          >
            ← Try again
          </Link>
        </div>
      </main>
    )
  }

  // ── Idle / no report yet ───────────────────────────────────────────────────
  // This handles the brief gap between page load and the first poll result.

  if (!report) {
    return (
      <main className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
        <LoadingSpinner currentStep={null} />
      </main>
    )
  }

  // ── Complete — full dashboard ──────────────────────────────────────────────

  const pdfUrl = getPdfUrl(report.job_id)

  return (
    <div className="min-h-screen bg-gray-50">

      {/* ── Sticky top nav bar ────────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 bg-white border-b border-gray-200 shadow-sm">
        <div className="mx-auto max-w-3xl flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-3 min-w-0">
            <span className="text-lg font-bold text-gray-900 font-mono tracking-wide truncate">
              {report.ticker}
            </span>
            <span className="hidden sm:block text-xs text-gray-400">
              {new Date(report.generated_at).toLocaleString()}
            </span>
          </div>
          <Link
            to="/"
            className="shrink-0 rounded-md px-3 py-1.5 text-sm font-medium text-brand-600 border border-brand-200 hover:bg-brand-50 transition-colors"
          >
            ← New analysis
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-6 px-4 py-8">

        {/* ── Data sources + warnings ───────────────────────────────────── */}
        {(report.sources_used.length > 0 || report.warnings.length > 0) && (
          <div className="space-y-2">
            <DataSourcesBadge sources={report.sources_used} />
            <WarningFlags warnings={report.warnings} />
          </div>
        )}

        {/* ── Executive summary ─────────────────────────────────────────── */}
        <ExecutiveSummary
          recommendation={report.recommendation}
          executive_summary={report.executive_summary}
          rationale={report.rationale}
          disclaimer={report.disclaimer}
        />

        {/* ── Fundamental analysis ──────────────────────────────────────── */}
        <FundamentalPanel
          result={report.fundamental_result}
          explanation={report.fundamental_explanation}
        />

        {/* ── Technical analysis ────────────────────────────────────────── */}
        <TechnicalPanel
          result={report.technical_result}
          explanation={report.technical_explanation}
        />

        {/* ── News ──────────────────────────────────────────────────────── */}
        <NewsPanel
          newsItems={report.news_items}
          newsSummary={report.news_summary}
        />

        {/* ── PDF download (plan requirement: disclaimer must appear here) ─ */}
        <div className="card flex flex-col items-center gap-3 text-center">
          <h2 className="section-heading mb-0">Download Report</h2>
          <p className="text-sm text-gray-500">
            Save a full PDF copy of this analysis report for offline reading.
          </p>
          <a
            href={pdfUrl}
            download
            className="inline-block rounded-lg bg-brand-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 transition-colors"
          >
            ↓ Download PDF
          </a>
          {/* Mandatory disclaimer in the PDF download area (plan requirement) */}
          <p className="disclaimer">
            For informational purposes only. Not financial advice.
          </p>
        </div>

      </main>
    </div>
  )
}
