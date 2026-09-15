/**
 * RankingHistory — collapsible historical ranking snapshots for a portfolio.
 *
 * Renders as a card at the bottom of PortfolioDetail.  The outer list shows
 * all snapshots (date + trigger badge) from ``useRankingHistory``.  Clicking a
 * row expands it inline and lazy-loads the full entry table via
 * ``useRankingSnapshot`` — the fetch only fires when that row is first opened.
 *
 * Layout
 * ──────
 *   ▼ History  (collapsible section header)
 *   ┌────────────────────────────────────────┐
 *   │ Date              Trigger   Chevron    │  ← snapshot row (collapsed)
 *   ├────────────────────────────────────────┤
 *   │ Date              Trigger   Chevron    │  ← snapshot row (expanded)
 *   │   # · Ticker · Score · Rec             │    ↳ inline entry table
 *   └────────────────────────────────────────┘
 *
 * Lazy-load behaviour
 * ───────────────────
 *   ``useRankingSnapshot`` is called for the currently expanded snapshot ID.
 *   While loading, a spinner is shown inside the expanded row.
 *   Collapsing a row keeps the cached data in TanStack Query's cache so
 *   re-expanding is instant.
 *
 * States
 * ──────
 *   Loading list  — skeleton rows
 *   Error list    — inline error banner
 *   Empty list    — "No snapshots yet" message
 *   Section toggle — the whole History section can be collapsed/expanded via
 *                    the header chevron to keep the page uncluttered after many
 *                    snapshots accumulate.
 *
 * Props
 * ─────
 *   portfolioId — UUID of the portfolio whose history to display.
 */

import { useState } from 'react'
import { useRankingHistory, useRankingSnapshot } from '../../hooks/usePortfolios'
import type { RankingEntry } from '../../types/portfolio'

// ── Props ──────────────────────────────────────────────────────────────────────

interface RankingHistoryProps {
  portfolioId: string
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function RankingHistory({ portfolioId }: RankingHistoryProps) {
  // Whether the whole History section is open.
  const [sectionOpen, setSectionOpen] = useState(true)

  // Which snapshot row is currently expanded (by snapshot ID), or null.
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const { data: snapshots, isLoading, error } = useRankingHistory(portfolioId)

  function toggleRow(id: string) {
    setExpandedId((prev) => (prev === id ? null : id))
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="card overflow-hidden p-0">

      {/* ── Section header ────────────────────────────────────────────────── */}
      <button
        type="button"
        onClick={() => setSectionOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-gray-50 transition-colors"
        aria-expanded={sectionOpen}
        aria-controls="ranking-history-body"
      >
        <span className="text-sm font-semibold text-gray-700">History</span>
        <ChevronIcon open={sectionOpen} />
      </button>

      {/* ── Body ──────────────────────────────────────────────────────────── */}
      {sectionOpen && (
        <div id="ranking-history-body" className="border-t border-gray-200">

          {/* Loading skeleton */}
          {isLoading && (
            <ul aria-label="Loading history" className="divide-y divide-gray-100">
              {[1, 2].map((i) => (
                <li key={i} className="h-12 animate-pulse bg-gray-50" aria-hidden="true" />
              ))}
            </ul>
          )}

          {/* Error */}
          {error && (
            <div
              role="alert"
              className="px-4 py-3 text-sm text-red-600"
            >
              Could not load history: {error.message}
            </div>
          )}

          {/* Empty */}
          {!isLoading && !error && snapshots?.length === 0 && (
            <p className="px-4 py-4 text-sm text-gray-400">
              No snapshots yet. Refresh the portfolio to create the first one.
            </p>
          )}

          {/* Snapshot rows */}
          {snapshots && snapshots.length > 0 && (
            <ul className="divide-y divide-gray-100" aria-label="Ranking snapshots">
              {snapshots.map((snapshot) => {
                const isExpanded = expandedId === snapshot.id
                return (
                  <li key={snapshot.id}>
                    {/* ── Row header ──────────────────────────────────────── */}
                    <button
                      type="button"
                      onClick={() => toggleRow(snapshot.id)}
                      aria-expanded={isExpanded}
                      className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-gray-50 transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        {/* Date */}
                        <span className="text-sm text-gray-700 whitespace-nowrap">
                          {new Date(snapshot.snapshot_at).toLocaleString(undefined, {
                            year: 'numeric',
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                        {/* Trigger badge */}
                        <TriggerBadge trigger={snapshot.trigger} />
                      </div>
                      <ChevronIcon open={isExpanded} />
                    </button>

                    {/* ── Expanded entry table (lazy-loaded) ──────────────── */}
                    {isExpanded && (
                      <SnapshotEntries
                        portfolioId={portfolioId}
                        snapshotId={snapshot.id}
                      />
                    )}
                  </li>
                )
              })}
            </ul>
          )}

        </div>
      )}
    </div>
  )
}

// ── SnapshotEntries — lazy-loaded inner table ──────────────────────────────────

/**
 * Fetches and renders the ranked entries for one snapshot.
 * Rendered only when the parent row is expanded, so the query fires lazily.
 * Re-expanding uses the TanStack Query cache — no re-fetch.
 */
function SnapshotEntries({
  portfolioId,
  snapshotId,
}: {
  portfolioId: string
  snapshotId: string
}) {
  const { data: snapshot, isLoading, error } = useRankingSnapshot(portfolioId, snapshotId)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center px-4 py-4">
        <SpinnerIcon />
      </div>
    )
  }

  if (error || !snapshot) {
    return (
      <div
        role="alert"
        className="px-4 py-3 text-sm text-red-500"
      >
        Could not load snapshot: {error?.message ?? 'Unknown error'}
      </div>
    )
  }

  if (snapshot.entries.length === 0) {
    return (
      <p className="px-6 py-3 text-sm text-gray-400">No entries in this snapshot.</p>
    )
  }

  return (
    <div className="overflow-x-auto bg-gray-50 px-4 pb-3">
      <table className="w-full min-w-[480px] text-sm">
        <thead>
          <tr className="text-xs font-semibold uppercase tracking-wider text-gray-400">
            <th className="py-2 pr-4 text-center w-8">#</th>
            <th className="py-2 pr-4 text-left">Ticker</th>
            <th className="py-2 pr-4 text-right">Overall</th>
            <th className="py-2 pr-4 text-right">Fund.</th>
            <th className="py-2 pr-4 text-right">Tech.</th>
            <th className="py-2 pr-4 text-right">Sent.</th>
            <th className="py-2 text-center">Rec.</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {snapshot.entries.map((entry: RankingEntry) => (
            <tr key={entry.ticker} className="hover:bg-gray-100 transition-colors">
              <td className="py-2 pr-4 text-center font-mono text-xs text-gray-400">
                {entry.rank}
              </td>
              <td className="py-2 pr-4 font-mono font-semibold text-gray-800">
                {entry.ticker}
              </td>
              <td className="py-2 pr-4 text-right font-mono">
                <ScoreCell value={entry.overall_score} />
              </td>
              <td className="py-2 pr-4 text-right font-mono text-xs text-gray-500">
                <ScoreCell value={entry.fundamental_score} dim />
              </td>
              <td className="py-2 pr-4 text-right font-mono text-xs text-gray-500">
                <ScoreCell value={entry.technical_score} dim />
              </td>
              <td className="py-2 pr-4 text-right font-mono text-xs text-gray-500">
                <ScoreCell value={entry.sentiment_score} dim />
              </td>
              <td className="py-2 text-center">
                <SnapshotRecBadge rec={entry.recommendation} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

/** Score cell: renders the value to 1 dp, or "—" when null. */
function ScoreCell({ value, dim = false }: { value: number | null; dim?: boolean }) {
  if (value == null) {
    return <span className="text-gray-300">—</span>
  }
  return (
    <span className={dim ? 'text-gray-500' : 'text-gray-800'}>
      {value.toFixed(1)}
    </span>
  )
}

/** Compact recommendation badge for the snapshot table. */
function SnapshotRecBadge({ rec }: { rec: string | null }) {
  if (!rec) return <span className="text-gray-300 text-xs">—</span>
  const cls =
    rec === 'Buy' ? 'badge-buy' : rec === 'Sell' ? 'badge-sell' : 'badge-hold'
  return <span className={`${cls} text-xs px-2 py-0.5`}>{rec}</span>
}

/** "manual" → blue pill; "quarterly" → purple pill. */
function TriggerBadge({ trigger }: { trigger: string }) {
  const isQuarterly = trigger === 'quarterly'
  return (
    <span
      className={[
        'inline-block rounded-full px-2 py-0.5 text-xs font-medium',
        isQuarterly
          ? 'bg-purple-100 text-purple-700'
          : 'bg-blue-100 text-blue-700',
      ].join(' ')}
    >
      {isQuarterly ? 'Quarterly' : 'Manual'}
    </span>
  )
}

/** Animated rotating chevron — points down when open, right when closed. */
function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={[
        'h-4 w-4 text-gray-400 transition-transform duration-200',
        open ? 'rotate-180' : 'rotate-0',
      ].join(' ')}
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M5.22 8.22a.75.75 0 011.06 0L10 11.94l3.72-3.72a.75.75 0 111.06 1.06l-4.25 4.25a.75.75 0 01-1.06 0L5.22 9.28a.75.75 0 010-1.06z"
        clipRule="evenodd"
      />
    </svg>
  )
}

function SpinnerIcon() {
  return (
    <svg
      className="h-5 w-5 animate-spin text-brand-500"
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
