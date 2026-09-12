/**
 * TanStack Query hook for submitting and polling a stock analysis job.
 *
 * Full implementation (mutation + polling refetch logic) is added in
 * Sub-Task 7. This stub exports the hook signature so other modules
 * can import it without TypeScript errors during earlier sub-tasks.
 */

import { useQuery } from '@tanstack/react-query'
import { getReport } from '../services/api'
import type { JobStatusResponse, ReportPayload } from '../types'

/**
 * Fetches the report payload for a given job ID and polls until the
 * job status transitions to 'complete' or 'error'.
 */
export function useAnalysis(jobId: string | undefined) {
  return useQuery<JobStatusResponse | ReportPayload>({
    queryKey: ['report', jobId],
    queryFn: () => getReport(jobId!),
    enabled: Boolean(jobId),
    // Polling interval — will be refined in Sub-Task 7.
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'complete' || status === 'error' ? false : 2000
    },
  })
}
