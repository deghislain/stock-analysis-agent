/**
 * Report page — dashboard shown after analysis completes.
 *
 * This is a minimal stub. Full implementation is in Sub-Task 7.
 */

import { useParams } from 'react-router-dom'

export default function Report() {
  const { jobId } = useParams<{ jobId: string }>()

  return (
    <main className="min-h-screen bg-gray-50 p-6">
      <div className="card max-w-4xl mx-auto text-center">
        <p className="text-gray-500 text-sm">
          Report dashboard for job <code className="font-mono">{jobId}</code>{' '}
          coming in Sub-Task 7.
        </p>
      </div>
    </main>
  )
}
