/**
 * TypeScript type definitions for the Stock Analysis Agent frontend.
 *
 * These interfaces mirror the Pydantic schemas defined in
 * backend/app/schemas/. Full definitions are added in Sub-Task 7.
 */

// ── Job / analysis ─────────────────────────────────────────────────────────

/** Possible states of a background analysis job. */
export type JobStatus = 'pending' | 'running' | 'complete' | 'error'

/** Response returned by POST /api/analyse. */
export interface AnalyseResponse {
  job_id: string
  status: JobStatus
}

/** Response returned by GET /api/report/{job_id} once the job completes. */
export interface ReportPayload {
  job_id: string
  ticker: string
  status: JobStatus
  // Full fields (fundamental, technical, sentiment, summary, etc.)
  // are populated in Sub-Task 7.
  [key: string]: unknown
}

/** Response returned by GET /api/validate/{ticker}. */
export interface ValidateResponse {
  valid: boolean
  name: string | null
}
