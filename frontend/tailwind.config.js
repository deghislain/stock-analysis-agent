/** @type {import('tailwindcss').Config} */
export default {
  // Tailwind scans these files and removes any unused utility classes from the
  // production CSS bundle — keeping the output as small as possible.
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      // Project-specific colour tokens used across all components.
      colors: {
        brand: {
          50:  '#eff6ff',
          100: '#dbeafe',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
        },
        buy:  '#16a34a', // green-600  — Buy recommendation badge
        hold: '#ca8a04', // yellow-600 — Hold recommendation badge
        sell: '#dc2626', // red-600    — Sell recommendation badge
      },
    },
  },
  plugins: [],
}
