/**
 * API client functions for the stock screener.
 *
 *   getIndustries()           GET  /api/screener/industries
 *   searchStocks(req)         POST /api/screener/search
 *
 * Both functions use the same shared Axios instance from api.ts so the
 * interceptor and error-handling behaviour is identical.
 */

import axios, { type AxiosError } from 'axios'
import type { ScreenerRequest, ScreenerResponse } from '../types/screener'

// Reuse the same base config as the main API client.
const client = axios.create({
  baseURL: '',
  headers: { 'Content-Type': 'application/json' },
  validateStatus: (status) => status < 500,
})

client.interceptors.response.use(
  (response) => {
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
    const message = error.message ?? 'Network error — could not reach the backend.'
    return Promise.reject(new Error(message))
  },
)

/**
 * Fetch the list of available industry / sector names for the dropdown.
 * Calls GET /api/screener/industries.
 */
export async function getIndustries(): Promise<string[]> {
  const { data } = await client.get<string[]>('/api/screener/industries')
  return data
}

/**
 * Search for stocks matching the given industry and price range.
 * Calls POST /api/screener/search.
 *
 * This can take 5–30 s depending on the number of candidates in the
 * selected industry — always call behind a loading indicator.
 */
export async function searchStocks(req: ScreenerRequest): Promise<ScreenerResponse> {
  const { data } = await client.post<ScreenerResponse>('/api/screener/search', req)
  return data
}
