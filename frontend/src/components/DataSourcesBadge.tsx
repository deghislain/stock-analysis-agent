/**
 * DataSourcesBadge — small pill badges listing every data source used to
 * produce this report (e.g. "Yahoo Finance", "Stooq", "DuckDuckGo").
 *
 * Sources come from ReportPayload.sources_used — a plain string array.
 * When the array is empty, nothing is rendered (the component returns null).
 *
 * Props
 * ─────
 *   sources — array of source name strings from ReportPayload.sources_used
 */

interface DataSourcesBadgeProps {
  sources: string[]
}

export default function DataSourcesBadge({ sources }: DataSourcesBadgeProps) {
  if (sources.length === 0) return null

  return (
    <div className="flex flex-wrap items-center gap-2" aria-label="Data sources used">
      <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">
        Sources:
      </span>
      {sources.map((source) => (
        <span
          key={source}
          className="inline-block rounded-full bg-gray-100 px-3 py-0.5 text-xs text-gray-600"
        >
          {source}
        </span>
      ))}
    </div>
  )
}
