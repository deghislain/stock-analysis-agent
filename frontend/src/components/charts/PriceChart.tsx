/**
 * PriceChart — Chart.js line chart showing closing price history with
 * SMA(20) and SMA(50) overlays over the full date range returned by the backend.
 *
 * Chart.js components are registered locally so this file is self-contained
 * and can be imported without touching main.tsx.
 *
 * Props
 * ─────
 *   dates        — ISO-8601 date strings from TechnicalResult.dates (x-axis labels)
 *   closePrices  — closing price series aligned to dates; null = warm-up bar (skipped)
 *   sma20        — SMA(20) values aligned to dates; null entries are skipped
 *   sma50        — SMA(50) values aligned to dates; null entries are skipped
 */

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  type ChartOptions,
  type ChartData,
} from 'chart.js'
import { Line } from 'react-chartjs-2'

// Register only the Chart.js components this chart needs.
ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend)

// ── Props ─────────────────────────────────────────────────────────────────────

interface PriceChartProps {
  dates: string[]
  closePrices: (number | null)[]
  sma20: (number | null)[]
  sma50: (number | null)[]
}

// ── Chart options (static — defined outside the component to avoid re-creation) ──

const OPTIONS: ChartOptions<'line'> = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: {
    /** Show all dataset values at the hovered x position together. */
    mode: 'index',
    intersect: false,
  },
  plugins: {
    legend: {
      position: 'top',
      labels: { font: { size: 12 }, boxWidth: 16 },
    },
    title: { display: false },
    tooltip: {
      callbacks: {
        /** Format price values as US dollars to 2 decimal places. */
        label: (ctx) =>
          `${ctx.dataset.label}: $${(ctx.parsed.y as number).toFixed(2)}`,
      },
    },
  },
  scales: {
    x: {
      ticks: {
        maxTicksLimit: 8,
        font: { size: 11 },
      },
      grid: { color: '#f0f0f0' },
    },
    y: {
      ticks: {
        font: { size: 11 },
        callback: (v) => `$${v}`,
      },
      grid: { color: '#f0f0f0' },
    },
  },
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function PriceChart({ dates, closePrices, sma20, sma50 }: PriceChartProps) {
  const data: ChartData<'line'> = {
    labels: dates,
    datasets: [
      {
        label: 'Close',
        data: closePrices,
        borderColor: '#3b82f6',   // blue-500
        backgroundColor: 'transparent',
        borderWidth: 2,
        pointRadius: 0,           // hide individual points for cleaner look
        tension: 0.2,
        spanGaps: false,          // null values create a gap — warm-up bars are excluded
      },
      {
        label: 'SMA 20',
        data: sma20,
        borderColor: '#f59e0b',   // amber-400
        backgroundColor: 'transparent',
        borderWidth: 1.5,
        borderDash: [4, 3],
        pointRadius: 0,
        tension: 0.2,
        spanGaps: false,
      },
      {
        label: 'SMA 50',
        data: sma50,
        borderColor: '#8b5cf6',   // violet-500
        backgroundColor: 'transparent',
        borderWidth: 1.5,
        borderDash: [6, 4],
        pointRadius: 0,
        tension: 0.2,
        spanGaps: false,
      },
    ],
  }

  return (
    <div className="relative h-64 w-full">
      <Line data={data} options={OPTIONS} />
    </div>
  )
}
