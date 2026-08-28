/**
 * Root application component.
 *
 * Defines the client-side routing structure using React Router v6:
 *   /                   → Home page  (ticker entry)
 *   /report/:jobId      → Report page (dashboard + PDF download)
 *   *                   → Redirects unknown paths back to Home
 *
 * This component is intentionally minimal — it only owns routing.
 * All layout and business logic lives in the individual page components.
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'

import Home from './pages/Home'
import Report from './pages/Report'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Landing page: ticker entry form */}
        <Route path="/" element={<Home />} />

        {/* Report dashboard: shown after a job completes */}
        <Route path="/report/:jobId" element={<Report />} />

        {/* Catch-all: redirect any unknown URL to Home */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
