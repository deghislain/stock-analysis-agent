/**
 * Root application component.
 *
 * Defines the client-side routing structure using React Router v6:
 *   /                   → Home page  (ticker entry)
 *   /report/:jobId      → Report page (dashboard + PDF download)
 *   /portfolio          → Portfolio page (two-panel portfolio manager)
 *   /screener           → Screener page (undervalued growth stock search)
 *   /watchlist          → Watchlist page (candidate comparison)
 *   *                   → Redirects unknown paths back to Home
 */

import { BrowserRouter, Routes, Route, Navigate, NavLink, Outlet } from 'react-router-dom'

import Home from './pages/Home'
import Report from './pages/Report'
import Portfolio from './pages/Portfolio'
import Screener from './pages/Screener'
import Watchlist from './pages/Watchlist'

// ── Shared nav layout ─────────────────────────────────────────────────────────

/**
 * Renders the shared top navigation bar above whichever child route is active.
 * Used for the "/" and "/portfolio" routes only.
 *
 * React Router's ``<NavLink>`` is used (not a plain ``<a>``) so the active tab
 * is highlighted automatically without any manual ``active`` prop threading.
 */
function WithNav() {
  return (
    <div className="flex min-h-screen flex-col bg-gray-50">

      {/* ── Top navigation bar ──────────────────────────────────────────── */}
      <header className="shrink-0 border-b border-gray-200 bg-white shadow-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">

          {/* Brand */}
          <span className="text-base font-semibold text-gray-900">
            Stock Analysis Agent
          </span>

          {/* Tab links */}
          <nav className="flex items-center gap-1" aria-label="Main navigation">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                [
                  'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-brand-50 text-brand-700'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
                ].join(' ')
              }
            >
              Analysis
            </NavLink>
            <NavLink
              to="/portfolio"
              className={({ isActive }) =>
                [
                  'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-brand-50 text-brand-700'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
                ].join(' ')
              }
            >
              Portfolio
            </NavLink>
            <NavLink
              to="/screener"
              className={({ isActive }) =>
                [
                  'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-brand-50 text-brand-700'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
                ].join(' ')
              }
            >
              Screener
            </NavLink>
            <NavLink
              to="/watchlist"
              className={({ isActive }) =>
                [
                  'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-brand-50 text-brand-700'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
                ].join(' ')
              }
            >
              Watchlist
            </NavLink>
          </nav>

        </div>
      </header>

      {/* Page content injected by React Router */}
      <Outlet />

    </div>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <BrowserRouter>
      <Routes>

        {/* Routes that share the top nav bar */}
        <Route element={<WithNav />}>
          <Route path="/" element={<Home />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/screener" element={<Screener />} />
          <Route path="/watchlist" element={<Watchlist />} />
        </Route>

        {/* Report has its own sticky header — no shared nav */}
        <Route path="/report/:jobId" element={<Report />} />

        {/* Catch-all: redirect any unknown URL to Home */}
        <Route path="*" element={<Navigate to="/" replace />} />

      </Routes>
    </BrowserRouter>
  )
}
