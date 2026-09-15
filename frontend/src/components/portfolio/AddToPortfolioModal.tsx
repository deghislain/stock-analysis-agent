/**
 * AddToPortfolioModal — add the current report's stock to a portfolio.
 *
 * Triggered from the Report page ("Add to Portfolio" button).  Lets the user
 * either pick an existing portfolio from a dropdown or create a brand-new one
 * inline before confirming the add.
 *
 * Props
 * ─────
 *   isOpen    — controls visibility.
 *   onClose   — called when the modal should close.
 *   ticker    — the ticker symbol being added (e.g. "AAPL").
 *   jobId     — the completed report's job ID; sent to POST .../stocks.
 *
 * Three-state UI
 * ──────────────
 *   "pick"    — default; shows the portfolio dropdown + optional "Create new"
 *               text input revealed by clicking "＋ Create new portfolio".
 *   "adding"  — useAddStock mutation is pending; controls disabled, spinner shown.
 *   "success" — mutation succeeded; brief confirmation then modal auto-closes.
 *
 * "Create new portfolio" option
 * ─────────────────────────────
 *   Clicking "＋ Create new portfolio" reveals an inline name field.
 *   On confirm:
 *     1. useCreatePortfolio fires.
 *     2. On success the returned portfolio ID is used immediately for useAddStock.
 *     3. Both mutations must succeed before the modal closes.
 *   The combined flow means the user never has to leave the modal or navigate
 *   to the Portfolio tab to create a portfolio first.
 *
 * Error handling
 * ──────────────
 *   409 (ticker already in portfolio) and 422 (job not complete) surface as an
 *   inline error banner below the dropdown.  The modal stays open so the user
 *   can choose a different portfolio or investigate.
 *
 * Keyboard / accessibility
 * ────────────────────────
 *   Escape closes without saving.  Backdrop click closes without saving.
 *   Submit button focused via ref on open for immediate keyboard access.
 */

import { useState, useEffect, useRef, type KeyboardEvent } from 'react'
import {
  usePortfolios,
  useCreatePortfolio,
  useAddStock,
} from '../../hooks/usePortfolios'

// ── Props ──────────────────────────────────────────────────────────────────────

interface AddToPortfolioModalProps {
  /** Whether the modal is visible. */
  isOpen: boolean
  /** Called when the modal should close. */
  onClose: () => void
  /** Ticker symbol being added (displayed in the title). */
  ticker: string
  /** Completed report job ID passed to POST .../stocks. */
  jobId: string
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function AddToPortfolioModal({
  isOpen,
  onClose,
  ticker,
  jobId,
}: AddToPortfolioModalProps) {
  const { data: portfolios, isLoading: portfoliosLoading } = usePortfolios()

  const createMutation = useCreatePortfolio()
  const addMutation = useAddStock()

  // ── Local state ────────────────────────────────────────────────────────────

  /** UUID of the selected portfolio from the dropdown, or "" when nothing chosen. */
  const [selectedId, setSelectedId] = useState<string>('')

  /** Whether the inline "create new" name field is visible. */
  const [showCreate, setShowCreate] = useState(false)

  /** Name for the new portfolio (used only when showCreate is true). */
  const [newName, setNewName] = useState('')

  /** Accumulated error message from either mutation. */
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  /** True after a successful add — shows brief confirmation before auto-close. */
  const [succeeded, setSucceeded] = useState(false)

  const confirmBtnRef = useRef<HTMLButtonElement>(null)

  // ── Reset on open ──────────────────────────────────────────────────────────

  useEffect(() => {
    if (isOpen) {
      // Pre-select the first portfolio if one exists so the modal is ready to confirm.
      setSelectedId(portfolios?.[0]?.id ?? '')
      setShowCreate(false)
      setNewName('')
      setErrorMsg(null)
      setSucceeded(false)
      createMutation.reset()
      addMutation.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

  // Update selectedId when portfolios load for the first time while open.
  useEffect(() => {
    if (isOpen && !selectedId && portfolios && portfolios.length > 0) {
      setSelectedId(portfolios[0].id)
    }
  }, [isOpen, portfolios, selectedId])

  // Focus confirm button on open for quick keyboard confirmation.
  useEffect(() => {
    if (isOpen) {
      const t = setTimeout(() => confirmBtnRef.current?.focus(), 50)
      return () => clearTimeout(t)
    }
  }, [isOpen])

  // ── Derived ────────────────────────────────────────────────────────────────

  const isPending = createMutation.isPending || addMutation.isPending

  // Confirm is enabled when:
  //  - not pending and not succeeded
  //  - if in "pick" mode: a portfolio is selected
  //  - if in "create" mode: new name is non-empty
  const canConfirm =
    !isPending &&
    !succeeded &&
    (showCreate ? newName.trim().length > 0 : selectedId !== '')

  // ── Submit ─────────────────────────────────────────────────────────────────

  async function handleConfirm() {
    if (!canConfirm) return
    setErrorMsg(null)

    try {
      let portfolioId = selectedId

      if (showCreate) {
        // Step 1 — create the portfolio.
        const created = await createMutation.mutateAsync({
          name: newName.trim(),
          description: '',
        })
        portfolioId = created.id
      }

      // Step 2 — add the stock to the (new or existing) portfolio.
      await addMutation.mutateAsync({
        portfolioId,
        body: { ticker, job_id: jobId },
      })

      setSucceeded(true)
      // Auto-close after a short confirmation pause.
      setTimeout(onClose, 1200)
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'An unexpected error occurred.')
    }
  }

  // ── Keyboard ───────────────────────────────────────────────────────────────

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Escape' && !isPending) onClose()
  }

  // ── Not open ───────────────────────────────────────────────────────────────

  if (!isOpen) return null

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={() => { if (!isPending) onClose() }}
      onKeyDown={handleKeyDown}
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-to-portfolio-title"
    >
      {/* Panel */}
      <div
        className="relative w-full max-w-sm rounded-xl bg-white p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Header ────────────────────────────────────────────────────── */}
        <div className="mb-5 flex items-center justify-between">
          <h2
            id="add-to-portfolio-title"
            className="text-base font-semibold text-gray-800"
          >
            Add{' '}
            <span className="font-mono text-brand-700">{ticker}</span>
            {' '}to Portfolio
          </h2>
          <button
            type="button"
            onClick={() => { if (!isPending) onClose() }}
            aria-label="Close"
            disabled={isPending}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 disabled:opacity-40 transition-colors"
          >
            <XIcon />
          </button>
        </div>

        {/* ── Success state ──────────────────────────────────────────────── */}
        {succeeded && (
          <div
            role="status"
            className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-3 py-3 text-sm text-green-700"
          >
            <CheckCircleIcon />
            <span>
              <span className="font-mono font-semibold">{ticker}</span>
              {' '}added successfully!
            </span>
          </div>
        )}

        {/* ── Main form (hidden once succeeded) ─────────────────────────── */}
        {!succeeded && (
          <div className="space-y-4">

            {/* Portfolio dropdown */}
            {!showCreate && (
              <div>
                <label
                  htmlFor="portfolio-select"
                  className="mb-1.5 block text-sm font-medium text-gray-700"
                >
                  Select portfolio
                </label>

                {/* Loading state */}
                {portfoliosLoading && (
                  <div className="flex h-9 items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 text-sm text-gray-400">
                    <SpinnerIcon className="h-4 w-4" />
                    Loading portfolios…
                  </div>
                )}

                {/* No portfolios yet — nudge to create one */}
                {!portfoliosLoading && portfolios?.length === 0 && (
                  <p className="text-sm text-gray-500">
                    No portfolios yet.{' '}
                    <button
                      type="button"
                      className="font-medium text-brand-600 hover:underline"
                      onClick={() => setShowCreate(true)}
                    >
                      Create one now →
                    </button>
                  </p>
                )}

                {/* Dropdown */}
                {!portfoliosLoading && portfolios && portfolios.length > 0 && (
                  <select
                    id="portfolio-select"
                    value={selectedId}
                    onChange={(e) => setSelectedId(e.target.value)}
                    disabled={isPending}
                    className={[
                      'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm',
                      'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500',
                      'disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed',
                    ].join(' ')}
                  >
                    {portfolios.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                        {p.stocks.length > 0
                          ? ` (${p.stocks.length} stock${p.stocks.length === 1 ? '' : 's'})`
                          : ''}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            )}

            {/* ── "Create new portfolio" inline form ─────────────────────── */}
            {showCreate && (
              <div>
                <label
                  htmlFor="new-portfolio-name"
                  className="mb-1.5 block text-sm font-medium text-gray-700"
                >
                  New portfolio name <span className="text-red-500">*</span>
                </label>
                <input
                  id="new-portfolio-name"
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleConfirm() }}
                  disabled={isPending}
                  maxLength={120}
                  placeholder="e.g. Tech Picks"
                  autoFocus
                  className={[
                    'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm',
                    'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500',
                    'disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed',
                  ].join(' ')}
                />
              </div>
            )}

            {/* Toggle: switch between "pick existing" and "create new" */}
            {!isPending && (
              <button
                type="button"
                onClick={() => {
                  setShowCreate((v) => !v)
                  setErrorMsg(null)
                }}
                className="text-sm text-brand-600 hover:underline"
              >
                {showCreate
                  ? '← Choose an existing portfolio'
                  : '＋ Create new portfolio'}
              </button>
            )}

            {/* Inline error */}
            {errorMsg && (
              <div
                role="alert"
                className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600"
              >
                {errorMsg}
              </div>
            )}
          </div>
        )}

        {/* ── Footer ────────────────────────────────────────────────────── */}
        {!succeeded && (
          <div className="mt-6 flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={isPending}
              className={[
                'rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium',
                'text-gray-700 bg-white hover:bg-gray-50 transition-colors',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              ].join(' ')}
            >
              Cancel
            </button>

            <button
              ref={confirmBtnRef}
              type="button"
              onClick={handleConfirm}
              disabled={!canConfirm}
              className={[
                'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold',
                'transition-colors',
                canConfirm
                  ? 'bg-brand-600 text-white hover:bg-brand-700 cursor-pointer'
                  : 'bg-gray-100 text-gray-400 cursor-not-allowed',
              ].join(' ')}
            >
              {isPending && <SpinnerIcon className="h-4 w-4" />}
              {showCreate ? 'Create & Add' : 'Add to Portfolio'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Icons ──────────────────────────────────────────────────────────────────────

function XIcon() {
  return (
    <svg className="h-5 w-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
    </svg>
  )
}

function CheckCircleIcon() {
  return (
    <svg className="h-5 w-5 shrink-0 text-green-600" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
    </svg>
  )
}

function SpinnerIcon({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  )
}
