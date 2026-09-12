/**
 * Axios API client for the Stock Analysis Agent backend.
 *
 * Four functions are exported — one per backend endpoint used by the frontend:
 *
 *   validateTicker(ticker)  GET  /api/validate/{ticker}
 *   analyseStock(ticker)    POST /api/analyse
 *   getReport(jobId)        GET  /api/report/{jobId}
 *   getPdfUrl(jobId)        pure URL helper — no network call
 *
 * A single shared Axios instance is used so the base URL and default headers
 * are configured in one place.  During development, Vite proxies /api/*
 * requests to http://localhost:8000 (configured in vite.config.ts), so
 * baseURL is left empty here and works identically in both dev and production.
 *
 * Error handling
 * ──────────────
 * Axios rejects on any HTTP error (4xx/5xx).  The caller (TanStack Query) is
 * responsible for catching and displaying errors — this module does not swallow
 * them.  The only special case is that the Axios instance attaches a response
 * interceptor that extracts the FastAPI `detail` string from error responses so
 * callers receive a useful message rather than the raw Axios error object.
 */

import axios, { type AxiosError } from 'axios'
import type {
  AnalyseResponse,
  JobStatusResponse,
  ReportPayload,
  ValidateResponse,
} from '../types'

// ── Shared Axios instance ──────────────────────────────────────────────────────

/**
 * All requests go through this instance.
 * baseURL is intentionally empty: Vite proxy (dev) and nginx (prod) both route
 * /api/* to the FastAPI backend without the frontend needing to know the host.
 */
const client = axios.create({
  baseURL: '',
  headers: { 'Content-Type': 'application/json' },
  // Allow the response interceptor below to handle 4xx/5xx before Axios rejects.
  validateStatus: (status) => status < 500,
})

/**
 * Response interceptor — converts FastAPI error shapes into plain Error objects.
 *
 * FastAPI returns `{ detail: string | object }` for 4xx responses.
 * This interceptor unwraps the `detail` field so all callers receive a
 * consistent Error with a human-readable message rather than a raw AxiosError.
 */
client.interceptors.response.use(
  (response) => {
    // Treat 4xx as errors (since validateStatus lets them through).
    if (response.status >= 400) {
      const detail = (response.data as { detail?: string })?.detail
      const message =
        typeof detail === 'string'
          ? detail
          : `Request failed with status ${response.status}`
      return Promise.reject(new Error(message))
    }
    return response
  },
  (error: AxiosError) => {
    // Network-level failures (no response received).
    const message =
      error.message ?? 'Network error — could not reach the backend.'
    return Promise.reject(new Error(message))
  },
)

// ── Endpoint functions ─────────────────────────────────────────────────────────

/**
 * Validate that a ticker symbol is real and return its display name.
 *
 * Calls GET /api/validate/{ticker}.
 * Always resolves (HTTP 200 for both valid and invalid tickers).
 * Rejects only on network errors or HTTP 422 (malformed ticker format).
 *
 * @param ticker  Raw ticker string — the backend normalises case.
 * @returns ValidateResponse with `valid`, `name`, and optionally `reason`.
 */
export async function validateTicker(ticker: string): Promise<ValidateResponse> {
  const { data } = await client.get<ValidateResponse>(
    `/api/validate/${encodeURIComponent(ticker)}`,
  )
  return data
}

/**
 * Submit a ticker for analysis and receive the new job ID.
 *
 * Calls POST /api/analyse.
 * Returns HTTP 202 with { job_id, status: "pending" } and starts the
 * background pipeline.  Poll getReport(jobId) to track progress.
 *
 * @param ticker  Ticker symbol to analyse (e.g. "AAPL", "BRK.B").
 * @returns AnalyseResponse with `job_id` and initial `status`.
 */
export async function analyseStock(ticker: string): Promise<AnalyseResponse> {
  const { data } = await client.post<AnalyseResponse>('/api/analyse', {
    ticker,
  })
  return data
}

/**
 * Poll the status of an analysis job or retrieve the completed report.
 *
 * Calls GET /api/report/{jobId}.
 *
 * The backend returns a different shape depending on job state:
 *   - status "pending" | "running" | "error"  →  JobStatusResponse
 *   - status "complete"                        →  ReportPayload
 *
 * TanStack Query's `refetchInterval` should be used to call this repeatedly
 * until the returned status is "complete" or "error".
 *
 * @param jobId  UUID string from analyseStock().
 * @returns JobStatusResponse (in progress) or ReportPayload (complete).
 */
export async function getReport(
  jobId: string,
): Promise<JobStatusResponse | ReportPayload> {
  const { data } = await client.get<JobStatusResponse | ReportPayload>(
    `/api/report/${encodeURIComponent(jobId)}`,
  )
  return data
}

/**
 * Return the URL for downloading the PDF report of a completed job.
 *
 * This is a pure URL builder — no network call is made.
 * Use the returned string as an <a href> or window.open() target.
 *
 * @param jobId  UUID string from analyseStock().
 * @returns Absolute-path URL, e.g. "/api/report/abc-123/pdf".
 */
export function getPdfUrl(jobId: string): string {
  return `/api/report/${encodeURIComponent(jobId)}/pdf`
}
