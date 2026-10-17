/**
 * Screener — Undervalued Growth Stock Search page.
 *
 * Layout
 * ──────
 *   • Criteria legend card — explains the Yahoo Finance undervalued-growth
 *     thresholds that every result has passed.
 *   • Search form card: industry autocomplete, min/max price, Search button.
 *   • Results table: PEG, Trailing P/E, Fwd P/E, P/B, price, revenue/EPS
 *     growth, profit margin — plus an "Analyse →" link per row.
 *
 * Every stock shown has passed ALL undervalued-growth criteria with available
 * data (P/E < 25, Fwd P/E < 15, PEG < 1, P/B < 1, revenue growth > 0 %,
 * earnings growth > 0 %).  Results are sorted by PEG ascending.
 */

import { useState, useEffect, useRef } from 'react'
import { getIndustries, searchStocks } from '../services/screenerApi'
import { analyseStock } from '../services/api'
import type { ScreenerCriterion, ScreenerStock } from '../types/screener'

// ── Formatters ─────────────────────────────────────────────────────────────────

function fmtPrice(v: number | null) {
  return v === null ? '—' : `$${v.toFixed(2)}`
}

function fmtCurrency(v: number | null) {
  if (v === null) return '—'
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`
  if (v >= 1e9)  return `$${(v / 1e9).toFixed(2)}B`
  if (v >= 1e6)  return `$${(v / 1e6).toFixed(2)}M`
  return `$${v.toLocaleString()}`
}

function fmtRatio(v: number | null, decimals = 2) {
  return v === null ? '—' : v.toFixed(decimals) + 'x'
}

function fmtPct(v: number | null) {
  if (v === null) return '—'
  const pct = (v * 100).toFixed(1)
  return `${v > 0 ? '+' : ''}${pct}%`
}

function growthClass(v: number | null) {
  if (v === null) return 'text-gray-400'
  return v > 0 ? 'text-green-600 font-medium' : 'text-red-500'
}

// ── Input class helper ─────────────────────────────────────────────────────────

function inputCls(hasError: boolean) {
  return [
    'w-full rounded-lg border px-4 py-2.5 text-sm bg-white',
    'transition-colors duration-150 focus:outline-none focus:ring-2',
    hasError
      ? 'border-red-400 focus:ring-red-300'
      : 'border-gray-300 focus:ring-brand-500',
  ].join(' ')
}

// ── CriteriaLegend sub-component ───────────────────────────────────────────────

function CriteriaLegend({ criteria }: { criteria: ScreenerCriterion[] }) {
  return (
    <div className="card space-y-3">
      <div>
        <h2 className="text-sm font-semibold text-gray-800">
          Undervalued Growth Criteria
        </h2>
        <p className="text-xs text-gray-500 mt-0.5">
          Every result below passes all of these filters (data from Yahoo Finance).
          Criteria are skipped — not failed — when data is unavailable for a ticker.
        </p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {criteria.map((c) => (
          <div
            key={c.label}
            className="flex items-start gap-2 rounded-lg border border-green-100 bg-green-50 px-3 py-2"
          >
            {/* Green checkmark */}
            <svg
              className="mt-0.5 h-4 w-4 shrink-0 text-green-500"
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                clipRule="evenodd"
              />
            </svg>
            <div className="min-w-0">
              <span className="text-xs font-semibold text-gray-800">
                {c.label}{' '}
                <span className="font-normal text-green-700">{c.threshold}</span>
              </span>
              <p className="text-xs text-gray-500 leading-snug mt-0.5">{c.rationale}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function Screener() {
  // ── Form state ───────────────────────────────────────────────────────────
  const [industry, setIndustry] = useState('')
  const [minPrice, setMinPrice] = useState('')
  const [maxPrice, setMaxPrice] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  // ── Industry autocomplete ────────────────────────────────────────────────
  const [industries, setIndustries] = useState<string[]>([])

  // ── Results state ────────────────────────────────────────────────────────
  const [results, setResults]     = useState<ScreenerStock[] | null>(null)
  const [criteria, setCriteria]   = useState<ScreenerCriterion[]>([])
  const [warnings, setWarnings]   = useState<string[]>([])
  const [total, setTotal]         = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError]         = useState<string | null>(null)

  // ── Per-row analyse state ────────────────────────────────────────────────
  // Tracks which tickers are currently submitting and which failed to start.
  const [analysingTickers, setAnalysingTickers] = useState<Set<string>>(new Set())
  const [analyseErrors, setAnalyseErrors]       = useState<Record<string, string>>({})

  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    getIndustries().then(setIndustries).catch(() => {})
  }, [])

  useEffect(() => () => { abortRef.current?.abort() }, [])

  // ── Validation ────────────────────────────────────────────────────────────

  function validate(): boolean {
    const errs: Record<string, string> = {}
    if (!industry.trim()) errs.industry = 'Please enter an industry or sector.'
    const min = parseFloat(minPrice)
    const max = parseFloat(maxPrice)
    if (isNaN(min) || min < 0) errs.minPrice = 'Enter a valid minimum price (≥ 0).'
    if (isNaN(max) || max < 0) errs.maxPrice = 'Enter a valid maximum price (≥ 0).'
    if (!isNaN(min) && !isNaN(max) && max <= min)
      errs.maxPrice = 'Maximum price must be greater than minimum price.'
    setFieldErrors(errs)
    return Object.keys(errs).length === 0
  }

  // ── Search ────────────────────────────────────────────────────────────────

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return

    abortRef.current?.abort()
    abortRef.current = new AbortController()
    setIsLoading(true)
    setError(null)
    setResults(null)
    setWarnings([])

    try {
      const resp = await searchStocks({
        industry: industry.trim(),
        min_price: parseFloat(minPrice),
        max_price: parseFloat(maxPrice),
      })
      setResults(resp.results)
      setTotal(resp.total)
      setCriteria(resp.criteria)
      setWarnings(resp.warnings)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unexpected error.')
    } finally {
      setIsLoading(false)
    }
  }

  // ── Analyse handler ───────────────────────────────────────────────────────
  // Submits POST /api/analyse for the ticker, then opens /report/:jobId in a
  // new browser tab. The tab is named after the ticker so repeated clicks on
  // the same stock reuse the same tab rather than opening a new one each time.

  async function handleAnalyse(ticker: string) {
    // Mark this row as submitting.
    setAnalysingTickers((prev) => new Set(prev).add(ticker))
    setAnalyseErrors((prev) => { const n = { ...prev }; delete n[ticker]; return n })

    try {
      const { job_id } = await analyseStock(ticker)
      // Open (or reuse) a tab named after the ticker and navigate to the report.
      window.open(`/report/${encodeURIComponent(job_id)}`, ticker)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Could not start analysis.'
      setAnalyseErrors((prev) => ({ ...prev, [ticker]: msg }))
    } finally {
      setAnalysingTickers((prev) => { const n = new Set(prev); n.delete(ticker); return n })
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <main className="min-h-screen bg-gray-50 px-4 py-8">
      <div className="mx-auto max-w-7xl space-y-6">

        {/* ── Page header ──────────────────────────────────────────────── */}
        <div className="space-y-1">
          <h1 className="text-2xl font-bold text-gray-900">
            Undervalued Growth Stock Screener
          </h1>
          <p className="text-sm text-gray-500">
            Find stocks that are growing fast AND trading below fair value.
            Criteria mirror the Yahoo Finance "Undervalued Growth Stocks" preset.
            Data sourced from Yahoo Finance — no API key required.
          </p>
          <p className="disclaimer text-xs">
            For informational purposes only. Not financial advice.
          </p>
        </div>

        {/* ── Static criteria legend (shown before first search) ───────── */}
        {criteria.length === 0 && (
          <CriteriaLegend
            criteria={[
              { label: 'Trailing P/E',    threshold: '0 – 20',       rationale: 'Reasonably priced relative to past 12-month earnings' },
              { label: '5-Year PEG Ratio',threshold: '< 1',          rationale: 'Growth At a Reasonable Price — P/E divided by 5-year EPS growth %' },
              { label: 'EPS Growth (LTM)',threshold: '≥ 25%',        rationale: 'Strong recent earnings-per-share expansion' },
              { label: 'Exchange',        threshold: 'NASDAQ / NYSE', rationale: 'Listed on major US exchanges for liquidity' },
            ]}
          />
        )}
        {criteria.length > 0 && <CriteriaLegend criteria={criteria} />}

        {/* ── Search form ───────────────────────────────────────────────── */}
        <div className="card">
          <form onSubmit={handleSearch} noValidate>
            <div className="grid gap-4 sm:grid-cols-3">

              {/* Industry */}
              <div>
                <label htmlFor="industry" className="block text-sm font-medium text-gray-700 mb-1">
                  Industry / Sector
                </label>
                <input
                  id="industry"
                  list="industry-list"
                  type="text"
                  placeholder="e.g. Semiconductors, Healthcare"
                  value={industry}
                  onChange={(e) => {
                    setIndustry(e.target.value)
                    if (fieldErrors.industry) setFieldErrors((p) => ({ ...p, industry: '' }))
                  }}
                  className={inputCls(!!fieldErrors.industry)}
                  autoComplete="off"
                />
                <datalist id="industry-list">
                  {industries.map((ind) => <option key={ind} value={ind} />)}
                </datalist>
                {fieldErrors.industry && (
                  <p className="mt-1 text-xs text-red-500">{fieldErrors.industry}</p>
                )}
              </div>

              {/* Min price */}
              <div>
                <label htmlFor="minPrice" className="block text-sm font-medium text-gray-700 mb-1">
                  Min Price (USD)
                </label>
                <input
                  id="minPrice"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="0"
                  value={minPrice}
                  onChange={(e) => {
                    setMinPrice(e.target.value)
                    if (fieldErrors.minPrice) setFieldErrors((p) => ({ ...p, minPrice: '' }))
                  }}
                  className={inputCls(!!fieldErrors.minPrice)}
                />
                {fieldErrors.minPrice && (
                  <p className="mt-1 text-xs text-red-500">{fieldErrors.minPrice}</p>
                )}
              </div>

              {/* Max price */}
              <div>
                <label htmlFor="maxPrice" className="block text-sm font-medium text-gray-700 mb-1">
                  Max Price (USD)
                </label>
                <input
                  id="maxPrice"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="500"
                  value={maxPrice}
                  onChange={(e) => {
                    setMaxPrice(e.target.value)
                    if (fieldErrors.maxPrice) setFieldErrors((p) => ({ ...p, maxPrice: '' }))
                  }}
                  className={inputCls(!!fieldErrors.maxPrice)}
                />
                {fieldErrors.maxPrice && (
                  <p className="mt-1 text-xs text-red-500">{fieldErrors.maxPrice}</p>
                )}
              </div>

            </div>

            {/* Submit */}
            <div className="mt-4 flex items-center gap-3">
              <button
                type="submit"
                disabled={isLoading}
                className={[
                  'rounded-lg px-5 py-2.5 text-sm font-semibold transition-colors duration-150',
                  isLoading
                    ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                    : 'bg-brand-600 text-white hover:bg-brand-700 cursor-pointer',
                ].join(' ')}
              >
                {isLoading ? 'Searching…' : 'Search'}
              </button>
              {isLoading && (
                <span className="text-sm text-gray-400 animate-pulse">
                  Applying undervalued-growth filters via Yahoo Finance…
                </span>
              )}
            </div>
          </form>
        </div>

        {/* ── Error ────────────────────────────────────────────────────── */}
        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* ── Warnings ──────────────────────────────────────────────────── */}
        {warnings.length > 0 && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 space-y-1">
            {warnings.map((w, i) => (
              <p key={i} className="text-sm text-amber-700">⚠ {w}</p>
            ))}
          </div>
        )}

        {/* ── Results table ─────────────────────────────────────────────── */}
        {results !== null && (
          <div className="card overflow-x-auto p-0">

            {/* Table header bar */}
            <div className="border-b border-gray-100 px-4 py-3 flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-gray-700">
                  {total === 0
                    ? 'No undervalued growth stocks found'
                    : `${total} undervalued growth stock${total !== 1 ? 's' : ''} found`}
                </h2>
                {total > 0 && (
                  <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                    All criteria passed
                  </span>
                )}
              </div>
              {total > 0 && (
                <span className="text-xs text-gray-400">
                  Sorted by PEG ratio (lowest first) · live data via Yahoo Finance
                </span>
              )}
            </div>

            {total > 0 && (
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                  <tr>
                    <th className="px-4 py-2 text-left">Ticker</th>
                    <th className="px-4 py-2 text-left">Name</th>
                    <th className="px-4 py-2 text-left hidden md:table-cell">Industry</th>
                    <th className="px-4 py-2 text-right">Price</th>
                    <th className="px-4 py-2 text-right hidden sm:table-cell">Mkt Cap</th>
                    {/* Valuation columns */}
                    <th className="px-4 py-2 text-right hidden lg:table-cell" title="PEG ratio — sorted by this">
                      PEG ↑
                    </th>
                    <th className="px-4 py-2 text-right hidden lg:table-cell" title="Trailing P/E (must be < 25)">
                      P/E
                    </th>
                    <th className="px-4 py-2 text-right hidden xl:table-cell" title="Forward P/E (must be < 15)">
                      Fwd P/E
                    </th>
                    <th className="px-4 py-2 text-right hidden xl:table-cell" title="Price-to-Book (must be < 1)">
                      P/B
                    </th>
                    {/* Growth columns */}
                    <th className="px-4 py-2 text-right hidden lg:table-cell" title="Revenue growth YoY (must be > 0%)">
                      Rev Growth
                    </th>
                    <th className="px-4 py-2 text-right hidden lg:table-cell" title="Earnings/EPS growth YoY (must be > 0%)">
                      EPS Growth
                    </th>
                    <th className="px-4 py-2 text-center">Analyse</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {results.map((stock) => (
                    <tr key={stock.ticker} className="hover:bg-gray-50 transition-colors">

                      <td className="px-4 py-2.5 font-mono font-semibold text-brand-700">
                        {stock.ticker}
                      </td>

                      <td className="px-4 py-2.5 text-gray-800 max-w-[160px] truncate">
                        {stock.name}
                      </td>

                      <td className="px-4 py-2.5 text-gray-500 hidden md:table-cell max-w-[150px] truncate">
                        {stock.industry ?? stock.sector ?? '—'}
                      </td>

                      <td className="px-4 py-2.5 text-right font-medium text-gray-900">
                        {fmtPrice(stock.current_price)}
                      </td>

                      <td className="px-4 py-2.5 text-right text-gray-600 hidden sm:table-cell">
                        {fmtCurrency(stock.market_cap)}
                      </td>

                      {/* PEG — primary sort key, highlighted */}
                      <td className="px-4 py-2.5 text-right hidden lg:table-cell">
                        {stock.peg_ratio !== null ? (
                          <span className="font-semibold text-green-700">
                            {fmtRatio(stock.peg_ratio)}
                          </span>
                        ) : '—'}
                      </td>

                      {/* Trailing P/E */}
                      <td className="px-4 py-2.5 text-right text-gray-600 hidden lg:table-cell">
                        {fmtRatio(stock.pe_ratio)}
                      </td>

                      {/* Forward P/E */}
                      <td className="px-4 py-2.5 text-right text-gray-600 hidden xl:table-cell">
                        {fmtRatio(stock.forward_pe)}
                      </td>

                      {/* P/B */}
                      <td className="px-4 py-2.5 text-right text-gray-600 hidden xl:table-cell">
                        {fmtRatio(stock.pb_ratio)}
                      </td>

                      {/* Revenue growth */}
                      <td className={`px-4 py-2.5 text-right hidden lg:table-cell ${growthClass(stock.revenue_growth)}`}>
                        {fmtPct(stock.revenue_growth)}
                      </td>

                      {/* EPS growth */}
                      <td className={`px-4 py-2.5 text-right hidden lg:table-cell ${growthClass(stock.eps_growth)}`}>
                        {fmtPct(stock.eps_growth)}
                      </td>

                      <td className="px-4 py-2.5 text-center">
                        {analyseErrors[stock.ticker] ? (
                          <span
                            className="text-xs text-red-500 cursor-pointer"
                            title={analyseErrors[stock.ticker]}
                            onClick={() => handleAnalyse(stock.ticker)}
                          >
                            Retry ↺
                          </span>
                        ) : analysingTickers.has(stock.ticker) ? (
                          <span className="text-xs text-gray-400 animate-pulse">
                            Starting…
                          </span>
                        ) : (
                          <button
                            onClick={() => handleAnalyse(stock.ticker)}
                            className="text-xs text-brand-600 hover:text-brand-800 font-medium underline underline-offset-2"
                            title={`Run full analysis on ${stock.ticker}`}
                          >
                            Analyse →
                          </button>
                        )}
                      </td>

                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

      </div>
    </main>
  )
}
