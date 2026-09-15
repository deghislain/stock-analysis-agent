/**
 * PortfolioList — left-sidebar list of all portfolios.
 *
 * Displays every portfolio as a selectable row with inline edit (pencil) and
 * delete (trash) action buttons.  A "New Portfolio" button at the bottom opens
 * ``PortfolioFormModal`` in create mode.
 *
 * Props
 * ─────
 *   selectedId        — UUID of the currently selected portfolio, or null.
 *   onSelect(id)      — called when the user clicks a portfolio row to select it.
 *
 * Behaviour
 * ─────────
 *   - Clicking a row calls ``onSelect`` with that portfolio's id so the parent
 *     (Portfolio page) can show the detail panel on the right.
 *   - The selected row is highlighted with a brand-blue left border and
 *     background tint.
 *   - Edit (pencil) button opens ``PortfolioFormModal`` in edit mode pre-filled
 *     with the existing name and description.
 *   - Delete (trash) button shows a ``window.confirm()`` dialog before calling
 *     ``useDeletePortfolio``; if the deleted portfolio was selected, ``onSelect``
 *     is called with null so the parent clears the detail panel.
 *   - Edit/delete buttons stop click propagation so they don't also select the row.
 *   - Loading state: skeleton rows are shown while the list is fetching.
 *   - Error state: an inline error banner is shown when the query fails.
 *   - Empty state: a friendly prompt to create the first portfolio.
 */

import { useState } from 'react'
import {
  usePortfolios,
  useDeletePortfolio,
} from '../../hooks/usePortfolios'
import PortfolioFormModal from './PortfolioFormModal'
import type { Portfolio } from '../../types/portfolio'

// ── Props ──────────────────────────────────────────────────────────────────────

interface PortfolioListProps {
  /** UUID of the currently selected portfolio, or null when none is selected. */
  selectedId: string | null
  /** Called when the user clicks a portfolio row or null after a deletion. */
  onSelect: (id: string | null) => void
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function PortfolioList({ selectedId, onSelect }: PortfolioListProps) {
  const { data: portfolios, isLoading, error } = usePortfolios()
  const deleteMutation = useDeletePortfolio()

  // Modal state — null means closed; a Portfolio object means edit mode.
  const [modalOpen, setModalOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Portfolio | undefined>(undefined)

  // ── Handlers ───────────────────────────────────────────────────────────────

  function openCreate() {
    setEditTarget(undefined)
    setModalOpen(true)
  }

  function openEdit(e: React.MouseEvent, portfolio: Portfolio) {
    e.stopPropagation()
    setEditTarget(portfolio)
    setModalOpen(true)
  }

  function handleDelete(e: React.MouseEvent, portfolio: Portfolio) {
    e.stopPropagation()
    if (
      !window.confirm(
        `Delete "${portfolio.name}"?\n\nThis will permanently remove the portfolio and all its stocks and ranking history.`,
      )
    ) {
      return
    }
    deleteMutation.mutate(portfolio.id, {
      onSuccess: () => {
        // Clear detail panel if the deleted portfolio was selected.
        if (selectedId === portfolio.id) onSelect(null)
      },
    })
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <aside className="flex h-full flex-col">
      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div className="mb-3 flex items-center justify-between px-1">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500">
          Portfolios
        </h2>
      </div>

      {/* ── List body ─────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto space-y-1">
        {/* Loading */}
        {isLoading && (
          <ul aria-label="Loading portfolios" className="space-y-1">
            {[1, 2, 3].map((i) => (
              <li
                key={i}
                className="h-14 animate-pulse rounded-lg bg-gray-100"
                aria-hidden="true"
              />
            ))}
          </ul>
        )}

        {/* Error */}
        {error && (
          <div
            role="alert"
            className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600"
          >
            Could not load portfolios: {error.message}
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !error && portfolios?.length === 0 && (
          <div className="rounded-lg border border-dashed border-gray-300 px-4 py-6 text-center">
            <p className="text-sm text-gray-500">No portfolios yet.</p>
            <p className="mt-1 text-xs text-gray-400">
              Click "New Portfolio" below to get started.
            </p>
          </div>
        )}

        {/* Portfolio rows */}
        {portfolios && portfolios.length > 0 && (
          <ul aria-label="Portfolio list">
            {portfolios.map((portfolio) => {
              const isSelected = portfolio.id === selectedId
              const isDeleting =
                deleteMutation.isPending &&
                deleteMutation.variables === portfolio.id

              return (
                <li key={portfolio.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(portfolio.id)}
                    disabled={isDeleting}
                    aria-current={isSelected ? 'true' : undefined}
                    className={[
                      'group relative w-full rounded-lg px-3 py-3 text-left',
                      'transition-colors duration-100',
                      isSelected
                        ? 'border-l-4 border-brand-600 bg-brand-50 pl-2.5'
                        : 'border-l-4 border-transparent hover:bg-gray-50',
                      isDeleting ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
                    ].join(' ')}
                  >
                    {/* Name */}
                    <span
                      className={[
                        'block truncate text-sm font-medium',
                        isSelected ? 'text-brand-700' : 'text-gray-800',
                      ].join(' ')}
                    >
                      {portfolio.name}
                    </span>

                    {/* Stock count */}
                    <span className="block text-xs text-gray-400 mt-0.5">
                      {portfolio.stocks.length === 0
                        ? 'No stocks'
                        : `${portfolio.stocks.length} stock${portfolio.stocks.length === 1 ? '' : 's'}`}
                    </span>

                    {/* Edit / Delete buttons — shown on row hover or focus-within */}
                    <span
                      className={[
                        'absolute inset-y-0 right-2 flex items-center gap-1',
                        'opacity-0 group-hover:opacity-100 group-focus-within:opacity-100',
                        'transition-opacity duration-100',
                      ].join(' ')}
                    >
                      <IconButton
                        label={`Edit "${portfolio.name}"`}
                        onClick={(e) => openEdit(e, portfolio)}
                        disabled={isDeleting}
                      >
                        <PencilIcon />
                      </IconButton>
                      <IconButton
                        label={`Delete "${portfolio.name}"`}
                        onClick={(e) => handleDelete(e, portfolio)}
                        disabled={isDeleting}
                        danger
                      >
                        {isDeleting ? <SpinnerIcon /> : <TrashIcon />}
                      </IconButton>
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {/* ── Footer: New Portfolio button ───────────────────────────────────── */}
      <div className="mt-3 border-t border-gray-200 pt-3">
        <button
          type="button"
          onClick={openCreate}
          className={[
            'flex w-full items-center justify-center gap-2',
            'rounded-lg border border-dashed border-gray-300 px-3 py-2.5',
            'text-sm font-medium text-gray-600',
            'hover:border-brand-400 hover:bg-brand-50 hover:text-brand-700',
            'transition-colors duration-150',
          ].join(' ')}
        >
          <PlusIcon />
          New Portfolio
        </button>
      </div>

      {/* ── Create / Edit modal ────────────────────────────────────────────── */}
      <PortfolioFormModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        portfolio={editTarget}
      />
    </aside>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

interface IconButtonProps {
  label: string
  onClick: (e: React.MouseEvent) => void
  disabled?: boolean
  danger?: boolean
  children: React.ReactNode
}

/** Small square icon button used for row-level actions. */
function IconButton({ label, onClick, disabled = false, danger = false, children }: IconButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className={[
        'rounded p-1 transition-colors',
        danger
          ? 'text-gray-400 hover:bg-red-50 hover:text-red-500'
          : 'text-gray-400 hover:bg-gray-200 hover:text-gray-600',
        disabled ? 'opacity-50 cursor-not-allowed' : '',
      ].join(' ')}
    >
      {children}
    </button>
  )
}

// ── Icons ──────────────────────────────────────────────────────────────────────

function PlusIcon() {
  return (
    <svg className="h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path d="M10.75 4.75a.75.75 0 00-1.5 0v4.5h-4.5a.75.75 0 000 1.5h4.5v4.5a.75.75 0 001.5 0v-4.5h4.5a.75.75 0 000-1.5h-4.5v-4.5z" />
    </svg>
  )
}

function PencilIcon() {
  return (
    <svg className="h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path d="M2.695 14.763l-1.262 3.154a.5.5 0 00.65.65l3.155-1.262a4 4 0 001.343-.885L17.5 5.5a2.121 2.121 0 00-3-3L3.58 13.42a4 4 0 00-.885 1.343z" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg className="h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022.841 10.518A2.75 2.75 0 007.596 19h4.807a2.75 2.75 0 002.742-2.53l.841-10.52.149.023a.75.75 0 00.23-1.482A41.03 41.03 0 0014 4.193V3.75A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 00-1.5.06l.3 7.5a.75.75 0 101.5-.06l-.3-7.5zm4.34.06a.75.75 0 10-1.5-.06l-.3 7.5a.75.75 0 101.5.06l.3-7.5z" clipRule="evenodd" />
    </svg>
  )
}

function SpinnerIcon() {
  return (
    <svg className="h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  )
}
