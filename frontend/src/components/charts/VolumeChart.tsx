/**
 * VolumeChart — Chart.js bar chart showing daily trading volume.
 *
 * Each bar is coloured green (#16a34a) when the closing price was higher
 * than the previous day's close, and red (#dc2626) when it was lower or
 * unchanged. This matches how traditional stock charts colour volume bars,
 * giving beginners an instant visual link between price movement and activity.
 *
 * Chart.js components are registered locally.
 *
 * Props
 * ─────
 *   dates        — ISO-8601 date strings (x-axis labels)
 *   volumes      — raw daily volume values aligned to dates; null = no data
 *   closePrices  — closing prices aligned to dates; used only for colouring bars
 */

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  type ChartOptions,
  type ChartData,
} from 'chart.js'
import { Bar } from 'react-chartjs-2'

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend)

// ── Constants ─────────────────────────────────────────────────────────────────

/** Green bar: price closed higher than the previous day. */
const COLOR_UP = '#16a34a'
/** Red bar: price closed lower or unchanged vs the previous day. */
const COLOR_DOWN = '#dc2626'

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Build a per-bar colour array by comparing each close[i] against close[i-1].
 * The first bar always gets the neutral (up) colour because there is no prior day.
 */
function buildBarColours(closePrices: (number | null)[]): string[] {
  return closePrices.map((price, i) => {
    if (i === 0 || price === null) return COLOR_UP
    const prev = closePrices[i - 1]
    return prev !== null && price >= prev ? COLOR_UP : COLOR_DOWN
  })
}

/**
 * Format large volume numbers into compact notation, e.g. 123456789 → "123.5M".
 */
function formatVolume(v: number): string {
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`
  return String(v)
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface VolumeChartProps {
  dates: string[]
  volumes: (number | null)[]
  closePrices: (number | null)[]
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function VolumeChart({ dates, volumes, closePrices }: VolumeChartProps) {
  const barColours = buildBarColours(closePrices)

  const data: ChartData<'bar'> = {
    labels: dates,
    datasets: [
      {
        label: 'Volume',
        data: volumes,
        backgroundColor: barColours,
        borderWidth: 0,
        barPercentage: 0.9,
        categoryPercentage: 1.0,
      },
    ],
  }

  const options: ChartOptions<'bar'> = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx) => `Volume: ${formatVolume(ctx.parsed.y as number)}`,
        },
      },
    },
    scales: {
      x: {
        ticks: { maxTicksLimit: 8, font: { size: 11 } },
        grid: { display: false },
      },
      y: {
        ticks: {
          font: { size: 11 },
          callback: (v) => formatVolume(v as number),
        },
        grid: { color: '#f0f0f0' },
      },
    },
  }

  return (
    <div className="relative h-40 w-full">
      <Bar data={data} options={options} />
    </div>
  )
}
