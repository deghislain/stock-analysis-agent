/**
 * Axios API client for the Stock Analysis Agent backend.
 *
 * All HTTP calls go through this module so the base URL and default
 * headers are configured in one place. Full endpoint implementations
 * are added in Sub-Task 7.
 */

import axios from 'axios'
import type { AnalyseResponse, ReportPayload, ValidateResponse } from '../types'

/** Shared Axios instance — base URL is empty so Vite's proxy (dev) and
 *  nginx (production) both route /api/* to the FastAPI backend. */
const client = axios.create({
  baseURL: '',
  headers: { 'Content-Type': 'application/json' },
})

/** Validate that a ticker symbol exists and return its display name. */
export async function validateTicker(ticker: string): Promise<ValidateResponse> {
  const { data } = await client.get<ValidateResponse>(`/api/validate/${ticker}`)
  return data
}

/** Submit a ticker for analysis and receive a job ID. */
export async function submitAnalysis(ticker: string): Promise<AnalyseResponse> {
  const { data } = await client.post<AnalyseResponse>('/api/analyse', { ticker })
  return data
}

/** Poll for the completed report payload once a job finishes. */
export async function fetchReport(jobId: string): Promise<ReportPayload> {
  const { data } = await client.get<ReportPayload>(`/api/report/${jobId}`)
  return data
}

/** Return the URL to download the PDF report for a completed job. */
export function pdfDownloadUrl(jobId: string): string {
  return `/api/report/${jobId}/pdf`
}
