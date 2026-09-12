/**
 * ExecutiveSummary — top-of-report card showing the recommendation, rationale,
 * and mandatory disclaimer.
 *
 * Layout (top to bottom)
 * ──────────────────────
 *   1. Section heading ("Executive Summary")
 *   2. Recommendation badge — large pill, colour-coded:
 *        BUY  → green background  (--color-buy  / bg-green-600)
 *        HOLD → amber background  (--color-hold / bg-yellow-500)
 *        SELL → red background    (--color-sell / bg-red-600)
 *   3. Executive summary paragraph (2–3 sentence LLM overview)
 *   4. "Rationale" sub-heading + 3-sentence paragraph
 *   5. Disclaimer — small, muted, italic; always visible (plan requirement)
 *
 * Props
 * ─────
 *   recommendation      — "Buy" | "Hold" | "Sell"
 *   executive_summary   — 2–3 sentence beginner overview (may be empty string)
 *   rationale           — 3-sentence justification for the recommendation
 *   disclaimer          — hardcoded disclaimer string from the backend payload
 */

import type { Recommendation } from '../types'

// ── Badge config ──────────────────────────────────────────────────────────────

const BADGE_STYLES: Record<Recommendation, { className: string; label: string }> = {
  Buy: {
    className: 'bg-green-600 text-white',
    label: 'BUY',
  },
  Hold: {
    className: 'bg-yellow-500 text-gray-900',
    label: 'HOLD',
  },
  Sell: {
    className: 'bg-red-600 text-white',
    label: 'SELL',
  },
}

// ── Component ─────────────────────────────────────────────────────────────────

interface ExecutiveSummaryProps {
  recommendation: Recommendation
  executive_summary: string
  rationale: string
  disclaimer: string
}

export default function ExecutiveSummary({
  recommendation,
  executive_summary,
  rationale,
  disclaimer,
}: ExecutiveSummaryProps) {
  const badge = BADGE_STYLES[recommendation] ?? BADGE_STYLES.Hold

  return (
    <section className="card space-y-4" aria-labelledby="exec-summary-heading">
      {/* ── Section heading ────────────────────────────────────────────────── */}
      <h2 id="exec-summary-heading" className="section-heading">
        Executive Summary
      </h2>

      {/* ── Recommendation badge ───────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <span
          className={[
            'inline-flex items-center justify-center rounded-lg px-6 py-2',
            'text-2xl font-extrabold tracking-widest',
            badge.className,
          ].join(' ')}
          aria-label={`Recommendation: ${recommendation}`}
        >
          {badge.label}
        </span>
        <p className="text-sm text-gray-500">
          Overall recommendation based on fundamental, technical, and sentiment analysis.
        </p>
      </div>

      {/* ── Executive overview paragraph ──────────────────────────────────── */}
      {executive_summary && (
        <p className="text-sm leading-relaxed text-gray-700">
          {executive_summary}
        </p>
      )}

      {/* ── Rationale ─────────────────────────────────────────────────────── */}
      {rationale && (
        <div className="space-y-1 border-t border-gray-100 pt-4">
          <h3 className="text-sm font-semibold text-gray-800">Rationale</h3>
          <p className="text-sm leading-relaxed text-gray-700">{rationale}</p>
        </div>
      )}

      {/* ── Disclaimer (plan requirement: always visible in ExecutiveSummary) */}
      <p className="disclaimer border-t border-gray-100 pt-3">
        {disclaimer}
      </p>
    </section>
  )
}
