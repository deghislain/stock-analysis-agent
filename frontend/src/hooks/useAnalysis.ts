/**
 * useAnalysis — TanStack Query hook for the full stock analysis lifecycle.
 *
 * Lifecycle
 * ─────────
 *   1. Caller invokes `start(ticker)` — fires the `useMutation` that calls
 *      POST /api/analyse and stores the returned `job_id` in local state.
 *   2. As soon as `jobId` is set, a `useQuery` activates and polls
 *      GET /api/report/{jobId} every 2 seconds.
 *   3. Polling stops automatically when the backend returns
 *      status "complete" or "error".
 *   4. The hook returns a flat, discriminated result object that the
 *      calling component can render without knowing about TanStack internals.
 *
 * Return shape
 * ────────────
 *   start(ticker)   — fire the mutation; resets any previous job state first
 *   jobId           — UUID of the active job, or null before start() is called
 *   status          — current job status, or null while idle
 *   currentStep     — pipeline step label from JobStatusResponse, or null
 *   report          — full ReportPayload once status === "complete", else null
 *   error           — human-readable error message, or null
 *   isSubmitting    — true while the POST /api/analyse call is in flight
 *   isLoading       — true while polling is in flight AND not yet complete
 *
 * Usage
 * ─────
 *   const { start, status, currentStep, report, error, isSubmitting } =
 *     useAnalysis()
 *
 *   // On "Generate Report" click:
 *   start('AAPL')
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { analyseStock, getReport } from '../services/api'
import type { JobStatusResponse, ReportPayload } from '../types'

// ── Types ─────────────────────────────────────────────────────────────────────

/** Discriminated union narrowing the poll result to its two possible shapes. */
function isComplete(
  data: JobStatusResponse | ReportPayload | undefined,
): data is ReportPayload {
  return data?.status === 'complete'
}

function isTerminal(status: string | null | undefined): boolean {
  return status === 'complete' || status === 'error'
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Manages the full analysis lifecycle: submission → polling → completion.
 *
 * No arguments are required — the ticker is passed to `start()` at call time.
 */
export function useAnalysis() {
  const queryClient = useQueryClient()

  // jobId is the link between the mutation result and the polling query.
  // null means no job has been started in this session.
  const [jobId, setJobId] = useState<string | null>(null)

  // ── Mutation: POST /api/analyse ───────────────────────────────────────────

  const mutation = useMutation({
    mutationFn: (ticker: string) => analyseStock(ticker),
    onSuccess: (data) => {
      // Clear any stale poll data for this new job before activating the query.
      queryClient.removeQueries({ queryKey: ['report', data.job_id] })
      setJobId(data.job_id)
    },
  })

  // ── Query: GET /api/report/{jobId} with 2-second polling ─────────────────

  const pollQuery = useQuery<JobStatusResponse | ReportPayload>({
    queryKey: ['report', jobId],
    queryFn: () => getReport(jobId!),
    // Only activate once we have a jobId.
    enabled: jobId !== null,
    // Retry on network errors but not on application-level errors (404, etc.).
    retry: false,
    // Poll every 2 seconds; stop as soon as the job reaches a terminal state.
    refetchInterval: (query) => {
      const s = query.state.data?.status
      return isTerminal(s) ? false : 2000
    },
    // Keep the last successful response in the cache even after the interval
    // fires the next fetch — prevents flickering between renders.
    staleTime: 0,
  })

  // ── Derived state ─────────────────────────────────────────────────────────

  const pollData = pollQuery.data
  const pollStatus = pollData?.status ?? null

  // Extract current_step only when the job is running (JobStatusResponse shape).
  const currentStep =
    pollData && !isComplete(pollData) ? pollData.current_step : null

  // Report is only available once the backend returns the complete payload.
  const report = isComplete(pollData) ? pollData : null

  // Consolidate errors: prefer the poll error, fall back to the mutation error.
  const errorMessage =
    (pollQuery.error as Error | null)?.message ??
    (mutation.error as Error | null)?.message ??
    (pollStatus === 'error'
      ? ((pollData as JobStatusResponse | undefined)?.error ??
        'Analysis failed. Please try again.')
      : null)

  // ── Public API ────────────────────────────────────────────────────────────

  /**
   * Start a new analysis for the given ticker.
   *
   * Resets any previous job state so a fresh poll cycle begins.
   * Safe to call while a previous job is still in progress.
   */
  function start(ticker: string): void {
    // Clear previous job so the polling query deactivates and results reset.
    setJobId(null)
    mutation.reset()
    mutation.mutate(ticker)
  }

  return {
    /** Fire a new analysis. Resets all previous state. */
    start,
    /** UUID of the active job, or null when idle. */
    jobId,
    /** Current pipeline status, or null when idle. */
    status: (mutation.isPending ? 'pending' : pollStatus) as
      | 'pending'
      | 'running'
      | 'complete'
      | 'error'
      | null,
    /**
     * Human-readable label of the currently executing pipeline step.
     * Comes from JobStatusResponse.current_step.
     * null when not running (idle, complete, or error).
     */
    currentStep,
    /** Full report payload once status === "complete", else null. */
    report,
    /** Human-readable error message, or null when no error has occurred. */
    error: errorMessage,
    /** True while POST /api/analyse is in flight. */
    isSubmitting: mutation.isPending,
    /** True while polling is active and the report is not yet complete. */
    isLoading:
      mutation.isPending ||
      (jobId !== null && !isTerminal(pollStatus) && pollQuery.isFetching),
  }
}
