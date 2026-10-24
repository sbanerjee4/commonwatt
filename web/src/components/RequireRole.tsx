import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { getSession, type UiRole } from '../lib/session'

// Route guard: redirects to /signin when there's no session, and (optionally)
// when the session's role doesn't match the route. Enforces that a building
// user can't open /utility and vice versa (AC-6, AC-7).
export function RequireRole({ role, children }: { role: UiRole; children: ReactNode }) {
  const session = getSession()
  if (!session) {
    return <Navigate to="/signin" replace />
  }
  if (session.role !== role) {
    // Signed in but wrong workspace — send them to their own.
    return <Navigate to={session.role === 'utility' ? '/utility' : '/building'} replace />
  }
  return <>{children}</>
}
