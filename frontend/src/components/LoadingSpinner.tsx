/**
 * LoadingSpinner — animated progress indicator for the analysis pipeline.
 *
 * Receives the `currentStep` string from `JobStatusResponse.current_step`
 * (as returned by `useAnalysis`) and displays:
 *   • An animated spinner
 *   • A friendly label for the current step
 *   • A step counter ("Step N of 7") so the user knows how much is left
 *   • A visual progress bar proportional to the step index
 *
 * Backend step strings (from orchestrator.py) and their friendly labels
 * ──────────────────────────────────────────────────────────────────────
 *   "Fetching data"                       → "Fetching market data…"
 *   "Fetching news"                       → "Researching latest news…"
 *   "Analysing fundamentals & technicals" → "Analysing fundamentals & technicals…"
 *   "Scoring sentiment"                   → "Scoring news sentiment…"
 *   "Generating report"                   → "Generating report with AI…"
 *   "Generating PDF"                      → "Building PDF report…"
 *   null / "pending" / unknown            → "Starting analysis…"
 *
 * Props
 * ─────
 *   currentStep   — value of `JobStatusResponse.current_step`; null while
 *                   the job is pending or between steps
 *   ticker        — optional ticker symbol shown in the heading
 */

// ── Step map ──────────────────────────────────────────────────────────────────

/** Ordered list of pipeline steps in execution order. */
const PIPELINE_STEPS: { key: string; label: string }[] = [
  { key: 'Fetching data',                       label: 'Fetching market data…' },
  { key: 'Fetching news',                       label: 'Researching latest news…' },
  { key: 'Analysing fundamentals & technicals', label: 'Analysing fundamentals & technicals…' },
  { key: 'Scoring sentiment',                   label: 'Scoring news sentiment…' },
  { key: 'Generating report',                   label: 'Generating report with AI…' },
  { key: 'Generating PDF',                      label: 'Building PDF report…' },
]

const TOTAL_STEPS = PIPELINE_STEPS.length

/**
 * Return the 1-based index and friendly label for a given backend step string.
 * Falls back to step 1 / "Starting analysis…" when the step is not yet known.
 */
function resolveStep(currentStep: string | null): {
  index: number
  label: string
} {
  if (!currentStep) return { index: 1, label: 'Starting analysis…' }
  const idx = PIPELINE_STEPS.findIndex((s) => s.key === currentStep)
  if (idx === -1) return { index: 1, label: 'Starting analysis…' }
  return { index: idx + 1, label: PIPELINE_STEPS[idx].label }
}

// ── Component ─────────────────────────────────────────────────────────────────

interface LoadingSpinnerProps {
  /**
   * The `current_step` string from `JobStatusResponse`.
   * null while the job is pending (not yet running).
   */
  currentStep: string | null
  /** Optional ticker symbol displayed in the heading. */
  ticker?: string
}

export default function LoadingSpinner({
  currentStep,
  ticker,
}: LoadingSpinnerProps) {
  const { index, label } = resolveStep(currentStep)
  const progressPercent = Math.round((index / TOTAL_STEPS) * 100)

  return (
    <div className="flex flex-col items-center gap-6 py-12 px-4 text-center">
      {/* ── Spinner ──────────────────────────────────────────────────────── */}
      <div className="relative flex items-center justify-center">
        {/* Outer ring */}
        <svg
          className="h-16 w-16 animate-spin text-brand-500"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <circle
            className="opacity-20"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="3"
          />
          <path
            className="opacity-80"
            fill="currentColor"
            d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z"
          />
        </svg>
      </div>

      {/* ── Heading ───────────────────────────────────────────────────────── */}
      <div className="space-y-1">
        <h2 className="text-xl font-semibold text-gray-800">
          {ticker ? `Analysing ${ticker}` : 'Analysing…'}
        </h2>
        <p className="text-sm text-gray-500">
          This usually takes 15–30 seconds.
        </p>
      </div>

      {/* ── Current step label ────────────────────────────────────────────── */}
      <p
        className="text-base font-medium text-brand-600"
        aria-live="polite"
        aria-atomic="true"
      >
        {label}
      </p>

      {/* ── Progress bar + counter ────────────────────────────────────────── */}
      <div className="w-full max-w-sm space-y-1.5">
        <div
          className="h-2 w-full overflow-hidden rounded-full bg-gray-100"
          role="progressbar"
          aria-valuenow={progressPercent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Step ${index} of ${TOTAL_STEPS}`}
        >
          <div
            className="h-full rounded-full bg-brand-500 transition-all duration-700 ease-in-out"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
        <p className="text-right text-xs text-gray-400">
          Step {index} of {TOTAL_STEPS}
        </p>
      </div>

      {/* ── Completed steps list ──────────────────────────────────────────── */}
      <ol className="w-full max-w-sm space-y-1 text-left">
        {PIPELINE_STEPS.map((step, i) => {
          const stepNumber = i + 1
          const isDone    = stepNumber < index
          const isCurrent = stepNumber === index
          return (
            <li
              key={step.key}
              className={[
                'flex items-center gap-2 text-sm',
                isDone    ? 'text-green-600'  : '',
                isCurrent ? 'text-brand-600 font-medium' : '',
                !isDone && !isCurrent ? 'text-gray-300' : '',
              ].join(' ')}
            >
              <span className="flex-shrink-0 text-base leading-none" aria-hidden="true">
                {isDone    ? '✓' : isCurrent ? '›' : '·'}
              </span>
              {step.label}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
