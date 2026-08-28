/**
 * Application entry point.
 *
 * Responsibilities:
 * - Mount the React app into the #root DOM node.
 * - Wrap the app with TanStack Query's QueryClient provider so every
 *   component tree can use useQuery / useMutation / useAnalysis.
 * - Register all Chart.js components globally so individual chart files
 *   do not need to repeat the registration boilerplate.
 * - Import the global CSS (Tailwind base + custom properties).
 */

import React from 'react'
import ReactDOM from 'react-dom/client'

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  RadialLinearScale,
  Filler,
  Tooltip,
  Legend,
  TimeScale,
} from 'chart.js'
import { CandlestickController, OhlcController, CandlestickElement, OhlcElement } from 'chartjs-chart-financial'
import 'chartjs-adapter-date-fns'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import App from './App'
import './index.css'

// ── Chart.js global registration ─────────────────────────────────────────────
// Register every scale, element, and controller used across the app once here.
// Individual chart components can then call new Chart() / <Line /> / <Bar />
// without repeating this list.
ChartJS.register(
  // Scales
  CategoryScale,
  LinearScale,
  RadialLinearScale,
  TimeScale,
  // Elements
  PointElement,
  LineElement,
  BarElement,
  // Financial chart types (candlestick / OHLC)
  CandlestickController,
  OhlcController,
  CandlestickElement,
  OhlcElement,
  // Plugins
  Filler,
  Tooltip,
  Legend,
)

// ── TanStack Query client ─────────────────────────────────────────────────────
// Single client instance shared across the whole app.
// staleTime: 0 — always re-fetch when a query mounts (analysis data changes).
// retry: 1    — retry once on network failure before showing an error.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 0,
      retry: 1,
    },
  },
})

// ── Mount ─────────────────────────────────────────────────────────────────────
const rootElement = document.getElementById('root')
if (!rootElement) {
  throw new Error('Root element #root not found. Check index.html.')
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
)
