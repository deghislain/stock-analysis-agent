/**
 * MetricsRadar — Chart.js radar chart that plots five normalised fundamental
 * health scores on a 0–100 scale, giving beginners a quick "at a glance"
 * visual snapshot of a company's fundamental health.
 *
 * Axes (in order, matching the radar spokes):
 *   1. P/E Ratio score   — lower P/E vs peers → higher score
 *   2. P/B Ratio score   — lower P/B vs peers → higher score
 *   3. Debt/Equity score — lower D/E → higher score
 *   4. Profit Margin     — higher margin → higher score
 *   5. Revenue Growth    — higher growth → higher score
 *
 * Scoring is done in the backend (FundamentalResult.score feeds the overall
 * composite, but per-axis scores are derived from the raw metric values here
 * using simple clamped-linear normalisation so the chart stays frontend-only).
 *
 * When any required value is null the component renders a plain "Data
 * unavailable" placeholder instead of a broken chart — per plan requirement.
 *
 * Chart.js components are registered locally.
 *
 * Props
 * ─────
 *   peRatio       — P/E ratio value (or null)
 *   pbRatio       — P/B ratio value (or null)
 *   debtToEquity  — Debt-to-equity ratio value (or null)
 *   profitMargin  — Profit margin as a decimal, e.g. 0.21 = 21% (or null)
 *   revenueGrowth — Revenue growth as a decimal, e.g. 0.08 = 8% (or null)
 */

import {
  Chart as ChartJS,
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
  type ChartOptions,
  type ChartData,
} from 'chart.js'
import { Radar } from 'react-chartjs-2'

ChartJS.register(RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend)

// ── Normalisation helpers ─────────────────────────────────────────────────────

/**
 * Clamp `value` between `min` and `max`, then map to 0–100.
 * Values ≤ min → 0; values ≥ max → 100.
 */
function normalise(value: number, min: number, max: number): number {
  return Math.round(Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100)))
}

/**
 * Score P/E ratio: lower is better for value investors.
 * 0 P/E (or negative) → 100; 50+ P/E → 0.
 */
function scorePE(pe: number): number {
  if (pe <= 0) return 50          // negative P/E = loss-making; neutral score
  return normalise(50 - pe, -50, 50) // inverted: low P/E → high score
}

/**
 * Score P/B ratio: lower is typically better.
 * ≤ 1 → 100; ≥ 10 → 0.
 */
function scorePB(pb: number): number {
  if (pb <= 0) return 50
  return normalise(10 - pb, 0, 9)
}

/**
 * Score debt-to-equity: lower is safer.
 * 0 → 100; ≥ 3 → 0.
 */
function scoreDE(de: number): number {
  if (de < 0) return 50           // negative D/E = unusual; neutral score
  return normalise(3 - de, 0, 3)
}

/**
 * Score profit margin: higher is better.
 * Input is a decimal (0.25 = 25%). 0% → 0; ≥ 40% → 100.
 */
function scoreMargin(margin: number): number {
  return normalise(margin * 100, 0, 40)
}

/**
 * Score revenue growth: higher is better.
 * Input is a decimal. 0% → 20 (baseline); ≥ 30% → 100; negative → 0.
 */
function scoreGrowth(growth: number): number {
  return normalise(growth * 100 + 5, 0, 30)
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface MetricsRadarProps {
  peRatio: number | null
  pbRatio: number | null
  debtToEquity: number | null
  profitMargin: number | null
  revenueGrowth: number | null
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function MetricsRadar({
  peRatio,
  pbRatio,
  debtToEquity,
  profitMargin,
  revenueGrowth,
}: MetricsRadarProps) {
  // Show placeholder when any required metric is missing.
  const hasData =
    peRatio !== null &&
    pbRatio !== null &&
    debtToEquity !== null &&
    profitMargin !== null &&
    revenueGrowth !== null

  if (!hasData) {
    return (
      <div className="flex h-56 w-full items-center justify-center rounded-lg bg-gray-50 text-sm text-gray-400">
        Fundamental data unavailable — radar chart cannot be displayed.
      </div>
    )
  }

  const scores = [
    scorePE(peRatio!),
    scorePB(pbRatio!),
    scoreDE(debtToEquity!),
    scoreMargin(profitMargin!),
    scoreGrowth(revenueGrowth!),
  ]

  const data: ChartData<'radar'> = {
    labels: ['P/E Ratio', 'P/B Ratio', 'Debt / Equity', 'Profit Margin', 'Revenue Growth'],
    datasets: [
      {
        label: 'Fundamental Score',
        data: scores,
        borderColor: '#3b82d4',
        backgroundColor: 'rgba(59,130,212,0.15)',
        borderWidth: 2,
        pointBackgroundColor: '#3b82d4',
        pointRadius: 4,
      },
    ],
  }

  const options: ChartOptions<'radar'> = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      r: {
        min: 0,
        max: 100,
        ticks: {
          stepSize: 25,
          font: { size: 10 },
          backdropColor: 'transparent',
        },
        pointLabels: { font: { size: 11 } },
        grid: { color: '#e5e7eb' },
      },
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx) => `Score: ${ctx.parsed.r} / 100`,
        },
      },
    },
  }

  return (
    <div className="relative h-56 w-full">
      <Radar data={data} options={options} />
    </div>
  )
}
