/**
 * TickerInput — stock ticker entry field with inline validation feedback.
 *
 * Validation is triggered on blur and on Enter keypress only (no debounce).
 * While the validation request is in flight the input and button are disabled
 * and a spinner is shown.
 *
 * Visual states
 * ─────────────
 *   idle          — neutral border, no feedback message
 *   validating    — spinner icon, input + button disabled, "Checking…" label
 *   valid         — green border + checkmark + company name
 *   invalid       — red border + ✕ icon + reason message
 *
 * Props
 * ─────
 *   onSubmit(ticker)  — called when the user clicks "Generate Report" on a
 *                        validated ticker; the ticker is already normalised
 *                        (trimmed, upper-cased by the backend)
 *   disabled          — when true the whole control is locked (e.g. while a
 *                        job is already running); defaults to false
 */

import { useState, useRef, useCallback, type KeyboardEvent } from 'react'
import { validateTicker } from '../services/api'

// ── Types ─────────────────────────────────────────────────────────────────────

type ValidationState =
  | { phase: 'idle' }
  | { phase: 'validating' }
  | { phase: 'valid'; name: string }
  | { phase: 'invalid'; reason: string }

// ── Component ─────────────────────────────────────────────────────────────────

interface TickerInputProps {
  /** Called with the normalised ticker when the user submits a valid symbol. */
  onSubmit: (ticker: string) => void
  /**
   * Lock the entire control (input + button).
   * Use while a job is already running to prevent duplicate submissions.
   */
  disabled?: boolean
}

export default function TickerInput({
  onSubmit,
  disabled = false,
}: TickerInputProps) {
  const [value, setValue] = useState('')
  const [validation, setValidation] = useState<ValidationState>({ phase: 'idle' })

  // Track the ticker that was last validated so re-focusing without changing
  // the input value does not fire a duplicate request.
  const lastValidatedRef = useRef<string>('')

  // ── Validation logic ───────────────────────────────────────────────────────

  const runValidation = useCallback(async (raw: string) => {
    const ticker = raw.trim().toUpperCase()

    // Nothing to validate.
    if (!ticker) {
      setValidation({ phase: 'idle' })
      lastValidatedRef.current = ''
      return
    }

    // Already validated this exact ticker — don't repeat the request.
    if (ticker === lastValidatedRef.current) return

    lastValidatedRef.current = ticker
    setValidation({ phase: 'validating' })

    try {
      const result = await validateTicker(ticker)
      if (result.valid) {
        setValidation({ phase: 'valid', name: result.name ?? ticker })
      } else {
        setValidation({
          phase: 'invalid',
          reason: result.reason ?? 'Symbol not found',
        })
      }
    } catch (err) {
      setValidation({
        phase: 'invalid',
        reason: err instanceof Error ? err.message : 'Validation failed',
      })
    }
  }, [])

  // ── Event handlers ─────────────────────────────────────────────────────────

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const next = e.target.value
    setValue(next)
    // Reset validation state when the user edits so the old result is not shown.
    if (next.trim().toUpperCase() !== lastValidatedRef.current) {
      setValidation({ phase: 'idle' })
      lastValidatedRef.current = ''
    }
  }

  function handleBlur() {
    runValidation(value)
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault()
      runValidation(value)
    }
  }

  function handleSubmit() {
    if (validation.phase === 'valid') {
      onSubmit(value.trim().toUpperCase())
    }
  }

  // ── Derived state ──────────────────────────────────────────────────────────

  const isValidating = validation.phase === 'validating'
  const isValid      = validation.phase === 'valid'
  const isInvalid    = validation.phase === 'invalid'
  const isLocked     = disabled || isValidating

  // Border colour driven by validation state.
  const inputBorder = isValid
    ? 'border-green-500 focus:ring-green-500'
    : isInvalid
      ? 'border-red-400 focus:ring-red-400'
      : 'border-gray-300 focus:ring-brand-500'

  return (
    <div className="w-full space-y-3">
      {/* ── Input row ─────────────────────────────────────────────────────── */}
      <div className="relative">
        <input
          type="text"
          value={value}
          onChange={handleChange}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          disabled={isLocked}
          placeholder="e.g. AAPL, BRK.B"
          maxLength={7}
          aria-label="Stock ticker symbol"
          aria-describedby="ticker-feedback"
          className={[
            'w-full rounded-lg border px-4 py-2.5 pr-10 text-sm font-mono',
            'uppercase tracking-wider placeholder:normal-case placeholder:tracking-normal',
            'bg-white transition-colors duration-150',
            'focus:outline-none focus:ring-2',
            'disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed',
            inputBorder,
          ].join(' ')}
        />

        {/* Right-side state icon */}
        <span
          className="pointer-events-none absolute inset-y-0 right-3 flex items-center"
          aria-hidden="true"
        >
          {isValidating && <Spinner />}
          {isValid      && <CheckIcon />}
          {isInvalid    && <XIcon />}
        </span>
      </div>

      {/* ── Inline feedback ───────────────────────────────────────────────── */}
      <div id="ticker-feedback" className="min-h-[1.25rem] text-sm">
        {isValidating && (
          <p className="text-gray-400">Checking symbol…</p>
        )}
        {isValid && (
          <p className="text-green-600 font-medium">
            {(validation as { phase: 'valid'; name: string }).name}
          </p>
        )}
        {isInvalid && (
          <p className="text-red-500">
            {(validation as { phase: 'invalid'; reason: string }).reason}
          </p>
        )}
      </div>

      {/* ── Submit button ─────────────────────────────────────────────────── */}
      <button
        type="button"
        onClick={handleSubmit}
        disabled={!isValid || isLocked}
        className={[
          'w-full rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors duration-150',
          isValid && !isLocked
            ? 'bg-brand-600 text-white hover:bg-brand-700 active:bg-brand-700 cursor-pointer'
            : 'bg-gray-100 text-gray-400 cursor-not-allowed',
        ].join(' ')}
      >
        Generate Report
      </button>

      {/* ── Ticker hint ───────────────────────────────────────────────────── */}
      <p className="text-center text-xs text-gray-400">
        US equities only &middot; standard tickers (AAPL) and multi-class formats (BRK.B) supported
      </p>
    </div>
  )
}

// ── Icon sub-components ───────────────────────────────────────────────────────

/** Animated spinner shown while validation is in flight. */
function Spinner() {
  return (
    <svg
      className="h-4 w-4 animate-spin text-gray-400"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-label="Validating"
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

/** Green checkmark shown when the ticker is valid. */
function CheckIcon() {
  return (
    <svg
      className="h-4 w-4 text-green-500"
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      aria-label="Valid"
    >
      <path
        fillRule="evenodd"
        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
        clipRule="evenodd"
      />
    </svg>
  )
}

/** Red ✕ shown when the ticker is invalid. */
function XIcon() {
  return (
    <svg
      className="h-4 w-4 text-red-400"
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      aria-label="Invalid"
    >
      <path
        fillRule="evenodd"
        d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
        clipRule="evenodd"
      />
    </svg>
  )
}
