/**
 * WarningFlags — renders a list of warning banners for missing or
 * potentially unreliable data, sourced from ReportPayload.warnings.
 *
 * Each warning is displayed as a yellow `.warning-banner` strip (defined in
 * index.css) so beginners immediately see when something may be incomplete.
 *
 * When the warnings array is empty the component returns null and nothing
 * is rendered — callers do not need to guard against an empty list.
 *
 * Props
 * ─────
 *   warnings — array of warning message strings from ReportPayload.warnings
 */

interface WarningFlagsProps {
  warnings: string[]
}

export default function WarningFlags({ warnings }: WarningFlagsProps) {
  if (warnings.length === 0) return null

  return (
    <ul className="space-y-2" aria-label="Data warnings">
      {warnings.map((message, i) => (
        <li key={i} className="warning-banner">
          {/* Warning icon — plain text triangle so no icon library is needed */}
          <span aria-hidden="true" className="mt-0.5 shrink-0">
            ⚠
          </span>
          <span>{message}</span>
        </li>
      ))}
    </ul>
  )
}
