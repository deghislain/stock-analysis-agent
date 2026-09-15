/**
 * PortfolioFormModal — create or edit a portfolio.
 *
 * Used in two modes, controlled by the ``portfolio`` prop:
 *
 *   Create mode  — ``portfolio`` is ``undefined``.
 *                  Title: "New Portfolio".  Submit calls ``useCreatePortfolio``.
 *   Edit mode    — ``portfolio`` is the existing ``Portfolio`` object.
 *                  Title: "Edit Portfolio".  Fields pre-filled.
 *                  Submit calls ``useUpdatePortfolio``.
 *
 * Props
 * ─────
 *   isOpen      — controls visibility; parent toggles this.
 *   onClose     — called when the modal should close (backdrop click, ✕ button,
 *                 Escape key, or after a successful submit).
 *   portfolio   — when provided, switches to edit mode and pre-fills the fields.
 *
 * Behaviour
 * ─────────
 *   - Name field is required (1–120 chars); the submit button stays disabled
 *     until the name is non-empty.
 *   - Description is optional; empty string is sent when blank.
 *   - Pressing Escape closes without saving.
 *   - Clicking the backdrop closes without saving.
 *   - The form resets to empty (create) or to original values (edit) each time
 *     ``isOpen`` transitions from false → true so stale input is never shown.
 *   - While the mutation is pending the submit button shows a spinner and both
 *     fields are disabled to prevent double-submission.
 *   - Mutation errors are displayed inline below the form fields.
 */

import { useEffect, useRef, type KeyboardEvent } from 'react'
import { useState } from 'react'
import { useCreatePortfolio, useUpdatePortfolio } from '../../hooks/usePortfolios'
import type { Portfolio } from '../../types/portfolio'

// ── Props ──────────────────────────────────────────────────────────────────────

interface PortfolioFormModalProps {
  /** Whether the modal is visible. */
  isOpen: boolean
  /** Called when the modal should close. */
  onClose: () => void
  /**
   * When provided, switches to edit mode and pre-fills the form fields.
   * When absent (undefined), the modal operates in create mode.
   */
  portfolio?: Portfolio
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function PortfolioFormModal({
  isOpen,
  onClose,
  portfolio,
}: PortfolioFormModalProps) {
  const isEditMode = portfolio !== undefined

  // ── Form state ─────────────────────────────────────────────────────────────

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  // Reset fields each time the modal opens so stale input is never shown.
  useEffect(() => {
    if (isOpen) {
      setName(portfolio?.name ?? '')
      setDescription(portfolio?.description ?? '')
    }
  }, [isOpen, portfolio])

  // ── Mutations ──────────────────────────────────────────────────────────────

  const createMutation = useCreatePortfolio()
  const updateMutation = useUpdatePortfolio()

  const isPending = createMutation.isPending || updateMutation.isPending
  const mutationError =
    (createMutation.error as Error | null)?.message ??
    (updateMutation.error as Error | null)?.message ??
    null

  // ── Submit ─────────────────────────────────────────────────────────────────

  function handleSubmit() {
    const trimmedName = name.trim()
    if (!trimmedName || isPending) return

    if (isEditMode) {
      updateMutation.mutate(
        {
          id: portfolio.id,
          body: {
            name: trimmedName,
            description: description.trim(),
          },
        },
        { onSuccess: onClose },
      )
    } else {
      createMutation.mutate(
        { name: trimmedName, description: description.trim() },
        { onSuccess: onClose },
      )
    }
  }

  // ── Keyboard handling ──────────────────────────────────────────────────────

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Escape') onClose()
  }

  // Focus the name input when the modal opens for immediate typing.
  const nameInputRef = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (isOpen) {
      // Small timeout so the element is visible before focus fires.
      const t = setTimeout(() => nameInputRef.current?.focus(), 50)
      return () => clearTimeout(t)
    }
  }, [isOpen])

  // ── Render ─────────────────────────────────────────────────────────────────

  if (!isOpen) return null

  const isSubmitDisabled = name.trim().length === 0 || isPending
  const title = isEditMode ? 'Edit Portfolio' : 'New Portfolio'
  const submitLabel = isEditMode ? 'Save Changes' : 'Create Portfolio'

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
      onKeyDown={handleKeyDown}
      role="dialog"
      aria-modal="true"
      aria-labelledby="portfolio-modal-title"
    >
      {/* Panel — stop click propagation so backdrop handler doesn't fire */}
      <div
        className="relative w-full max-w-md rounded-xl bg-white p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Header ──────────────────────────────────────────────────────── */}
        <div className="mb-5 flex items-center justify-between">
          <h2
            id="portfolio-modal-title"
            className="text-lg font-semibold text-gray-800"
          >
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close modal"
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
          >
            <XIcon />
          </button>
        </div>

        {/* ── Fields ──────────────────────────────────────────────────────── */}
        <div className="space-y-4">

          {/* Name */}
          <div>
            <label
              htmlFor="portfolio-name"
              className="mb-1 block text-sm font-medium text-gray-700"
            >
              Name <span className="text-red-500">*</span>
            </label>
            <input
              ref={nameInputRef}
              id="portfolio-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSubmit()
              }}
              disabled={isPending}
              maxLength={120}
              placeholder="e.g. Tech Picks"
              className={[
                'w-full rounded-lg border px-3 py-2 text-sm',
                'border-gray-300 bg-white',
                'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500',
                'disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed',
                'transition-colors',
              ].join(' ')}
            />
            <p className="mt-1 text-right text-xs text-gray-400">
              {name.length}/120
            </p>
          </div>

          {/* Description */}
          <div>
            <label
              htmlFor="portfolio-description"
              className="mb-1 block text-sm font-medium text-gray-700"
            >
              Description{' '}
              <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <textarea
              id="portfolio-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isPending}
              rows={3}
              placeholder="What is this portfolio for?"
              className={[
                'w-full rounded-lg border px-3 py-2 text-sm resize-none',
                'border-gray-300 bg-white',
                'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500',
                'disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed',
                'transition-colors',
              ].join(' ')}
            />
          </div>

          {/* Inline error */}
          {mutationError && (
            <p
              role="alert"
              className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-600"
            >
              {mutationError}
            </p>
          )}
        </div>

        {/* ── Footer actions ───────────────────────────────────────────────── */}
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
            type="button"
            onClick={handleSubmit}
            disabled={isSubmitDisabled}
            className={[
              'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold',
              'transition-colors',
              isSubmitDisabled
                ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                : 'bg-brand-600 text-white hover:bg-brand-700 cursor-pointer',
            ].join(' ')}
          >
            {isPending && <SpinnerIcon />}
            {submitLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Icons ──────────────────────────────────────────────────────────────────────

function XIcon() {
  return (
    <svg
      className="h-5 w-5"
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
        clipRule="evenodd"
      />
    </svg>
  )
}

function SpinnerIcon() {
  return (
    <svg
      className="h-4 w-4 animate-spin"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  )
}
