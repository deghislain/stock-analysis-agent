/**
 * NewsPanel — dashboard section listing recent news items fetched by the
 * ResearchAgent, plus the LLM-generated prose summary of those headlines.
 *
 * Each news item shows:
 *   • Title (links to the source URL, opens in a new tab)
 *   • Source domain and date, displayed as small muted metadata
 *
 * When the news list is empty, a neutral placeholder message is shown
 * instead of a blank card so beginners always see something meaningful.
 *
 * Props
 * ─────
 *   newsItems    — array of NewsItem objects from ReportPayload.news_items
 *   newsSummary  — LLM-generated prose summary (may be empty string)
 */

import type { NewsItem } from '../types'

// ── Props ─────────────────────────────────────────────────────────────────────

interface NewsPanelProps {
  newsItems: NewsItem[]
  newsSummary: string
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function NewsPanel({ newsItems, newsSummary }: NewsPanelProps) {
  return (
    <section className="card space-y-4" aria-labelledby="news-heading">
      {/* ── Heading ──────────────────────────────────────────────────────── */}
      <h2 id="news-heading" className="section-heading">
        Recent News
      </h2>

      {/* ── LLM prose summary ────────────────────────────────────────────── */}
      {newsSummary && (
        <p className="text-sm leading-relaxed text-gray-600 border-b border-gray-100 pb-4">
          {newsSummary}
        </p>
      )}

      {/* ── News item list ───────────────────────────────────────────────── */}
      {newsItems.length === 0 ? (
        <p className="text-sm text-gray-400">
          No recent news articles were found for this ticker.
        </p>
      ) : (
        <ul className="divide-y divide-gray-100 -mx-2">
          {newsItems.map((item, i) => (
            <li key={i} className="px-2 py-3">
              {/* Title — external link */}
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-medium text-blue-600 hover:underline leading-snug"
              >
                {item.title}
              </a>

              {/* Metadata row: source · date */}
              <p className="mt-1 text-xs text-gray-400">
                {item.source}
                {item.date && (
                  <>
                    {' · '}
                    {item.date}
                  </>
                )}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
