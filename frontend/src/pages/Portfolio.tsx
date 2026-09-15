/**
 * Portfolio — main portfolio tab page.
 *
 * The shared top navigation bar ("Analysis" / "Portfolio" tabs) is rendered
 * by the ``<WithNav>`` layout component in ``App.tsx``; this component only
 * owns the two-panel body below it.
 *
 * Layout
 * ──────
 *   Two-panel split (fills the remaining height below the shared nav):
 *
 *   ┌──────────────────┬─────────────────────────────────────────┐
 *   │  Sidebar (280px) │  Detail panel (flex-1)                  │
 *   │  PortfolioList   │  PortfolioDetail  OR  empty placeholder  │
 *   └──────────────────┴─────────────────────────────────────────┘
 *
 *   On narrow viewports (<= md / 768px) the sidebar takes the full width and
 *   the detail panel is hidden until a portfolio is selected, at which point
 *   the sidebar is hidden and the detail panel fills the screen.  A "← Back"
 *   link restores the list view on mobile.
 *
 * State
 * ─────
 *   selectedPortfolioId — UUID of the selected portfolio, or null.
 *   Owned here so PortfolioList and PortfolioDetail can stay stateless with
 *   respect to selection.
 */

import { useState } from 'react'
import PortfolioList from '../components/portfolio/PortfolioList'
import PortfolioDetail from '../components/portfolio/PortfolioDetail'

// ── Component ──────────────────────────────────────────────────────────────────

export default function Portfolio() {
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string | null>(null)

  // ── Render ─────────────────────────────────────────────────────────────────

  // The shared nav bar is rendered by <WithNav> in App.tsx above this component.
  // flex-1 fills the remaining height below that nav bar.
  return (
    <div className="flex flex-1 overflow-hidden">

      {/* ── Two-panel body ─────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/*
         * Sidebar — always visible on desktop; hidden on mobile when a
         * portfolio is selected (detail panel takes over).
         */}
        <aside
          className={[
            'flex flex-col border-r border-gray-200 bg-white',
            // Desktop: fixed 280px sidebar
            'md:w-72 md:shrink-0 md:flex md:overflow-y-auto',
            // Mobile: full-width, hidden when detail is showing
            selectedPortfolioId ? 'hidden md:flex' : 'flex w-full',
          ].join(' ')}
        >
          <div className="flex-1 overflow-y-auto p-4">
            <PortfolioList
              selectedId={selectedPortfolioId}
              onSelect={setSelectedPortfolioId}
            />
          </div>
        </aside>

        {/*
         * Detail panel — flex-1 on desktop; full screen on mobile when selected.
         */}
        <main
          className={[
            'flex flex-1 flex-col overflow-y-auto bg-gray-50',
            // Mobile: hidden when no portfolio selected (list shows instead)
            selectedPortfolioId ? 'flex' : 'hidden md:flex',
          ].join(' ')}
        >
          {selectedPortfolioId ? (
            <div className="flex-1 p-4 md:p-6">
              {/* Mobile "back to list" link */}
              <button
                type="button"
                onClick={() => setSelectedPortfolioId(null)}
                className="mb-4 flex items-center gap-1 text-sm font-medium text-brand-600 hover:underline md:hidden"
              >
                <ChevronLeftIcon />
                All Portfolios
              </button>

              <PortfolioDetail portfolioId={selectedPortfolioId} />
            </div>
          ) : (
            /* Empty-selection placeholder — desktop only (mobile shows the list) */
            <div className="hidden flex-1 items-center justify-center md:flex">
              <div className="text-center space-y-2">
                <p className="text-sm font-medium text-gray-500">
                  Select a portfolio to view its details
                </p>
                <p className="text-xs text-gray-400">
                  or create a new one using the sidebar
                </p>
              </div>
            </div>
          )}
        </main>

      </div>
    </div>
  )
}

// ── Icons ──────────────────────────────────────────────────────────────────────

function ChevronLeftIcon() {
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
        d="M11.78 5.22a.75.75 0 010 1.06L8.06 10l3.72 3.72a.75.75 0 11-1.06 1.06l-4.25-4.25a.75.75 0 010-1.06l4.25-4.25a.75.75 0 011.06 0z"
        clipRule="evenodd"
      />
    </svg>
  )
}
