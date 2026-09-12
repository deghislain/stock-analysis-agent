/**
 * RSIChart — Chart.js line chart for the RSI(14) momentum oscillator.
 *
 * Displays:
 *   • The RSI(14) line
 *   • A dashed horizontal reference line at 70 (overbought threshold)
 *   • A dashed horizontal reference line at 30 (oversold threshold)
 *   • A light red shaded band above 70 (overbought zone)
 *   • A light green shaded band below 30 (oversold zone)
 *
 * The shaded bands are implemented with Chart.js annotation plugin-free
 * approach: two additional "fill" datasets that paint between the threshold
 * and the y-axis boundary using `fill` + `backgroundColor`.
 *
 * Chart.js components are registered locally.
 *
 * Props
 * ─────
 *   dates   — ISO-8601 date strings (x-axis labels)
 *   rsi     — RSI(14) values aligned to dates; null entries = warm-up bars
 */

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Title,
  Tooltip,
  Legend,
  type ChartOptions,
  type ChartData,
} from 'chart.js'
import { Line } from 'react-chartjs-2'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Title,
  Tooltip,
  Legend,
)

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Fill an array of `length` elements with the constant `value`.
 * Used to draw the flat overbought/oversold reference bands.
 */
function fillConstant(length: number, value: number): number[] {
  return Array<number>(length).fill(value)
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface RSIChartProps {
  dates: string[]
  rsi: (number | null)[]
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function RSIChart({ dates, rsi }: RSIChartProps) {
  const len = dates.length

  const data: ChartData<'line'> = {
    labels: dates,
    datasets: [
      // ── Overbought shaded band (70 → 100) ───────────────────────────────
      {
        label: '_overbought_band',    // underscore prefix = hidden from legend
        data: fillConstant(len, 100),
        borderWidth: 0,
        pointRadius: 0,
        fill: { target: '+1', above: 'rgba(220,38,38,0.08)' }, // fill toward RSI-70 line
        backgroundColor: 'transparent',
      },
      // ── Overbought reference line (70) ──────────────────────────────────
      {
        label: 'Overbought (70)',
        data: fillConstant(len, 70),
        borderColor: 'rgba(220,38,38,0.5)',
        borderWidth: 1,
        borderDash: [5, 4],
        pointRadius: 0,
        backgroundColor: 'rgba(220,38,38,0.08)',
        fill: false,
      },
      // ── RSI(14) line ─────────────────────────────────────────────────────
      {
        label: 'RSI 14',
        data: rsi,
        borderColor: '#3b82f6',       // blue-500
        backgroundColor: 'transparent',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.2,
        spanGaps: false,
        fill: false,
      },
      // ── Oversold reference line (30) ─────────────────────────────────────
      {
        label: 'Oversold (30)',
        data: fillConstant(len, 30),
        borderColor: 'rgba(22,163,74,0.5)',
        borderWidth: 1,
        borderDash: [5, 4],
        pointRadius: 0,
        backgroundColor: 'rgba(22,163,74,0.08)',
        fill: false,
      },
      // ── Oversold shaded band (0 → 30) ────────────────────────────────────
      {
        label: '_oversold_band',
        data: fillConstant(len, 0),
        borderWidth: 0,
        pointRadius: 0,
        fill: { target: '-1', below: 'rgba(22,163,74,0.08)' }, // fill toward RSI-30 line
        backgroundColor: 'transparent',
      },
    ],
  }

  const options: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        position: 'top',
        labels: {
          font: { size: 11 },
          boxWidth: 14,
          filter: (item) => !item.text.startsWith('_'), // hide internal band datasets
        },
      },
      tooltip: {
        filter: (item) => !item.dataset.label?.startsWith('_'),
        callbacks: {
          label: (ctx) => {
            if (ctx.dataset.label === 'RSI 14') {
              return `RSI: ${(ctx.parsed.y as number).toFixed(1)}`
            }
            return `${ctx.dataset.label}`
          },
        },
      },
    },
    scales: {
      x: {
        ticks: { maxTicksLimit: 8, font: { size: 11 } },
        grid: { color: '#f0f0f0' },
      },
      y: {
        min: 0,
        max: 100,
        ticks: {
          stepSize: 20,
          font: { size: 11 },
        },
        grid: { color: '#f0f0f0' },
      },
    },
  }

  return (
    <div className="relative h-48 w-full">
      <Line data={data} options={options} />
    </div>
  )
}
