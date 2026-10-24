import { useEffect, useState, type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { getIdentity, refreshIdentity, type UiRole, type Identity } from '../lib/session'

// Route guard backed by the real cookie session. On mount it verifies the
// session against /auth/me (the cached identity is only a first guess, since a
// cookie can expire server-side). Redirects to /signin when signed out, and to
// the user's own workspace when the role doesn't match the route (AC-6, AC-7).
export function RequireRole({ role, children }: { role: UiRole; children: ReactNode }) {
  const [identity, setIdentity] = useState<Identity | null>(getIdentity())
  const [checked, setChecked] = useState(false)

  useEffect(() => {
    let active = true
    refreshIdentity().then((fresh) => {
      if (active) {
        setIdentity(fresh)
        setChecked(true)
      }
    })
    return () => {
      active = false
    }
  }, [])

  if (!checked && identity === null) {
    return <div className="route-loading">Loading…</div>
  }
  if (checked && identity === null) {
    return <Navigate to="/signin" replace />
  }
  if (identity && identity.role !== role) {
    return <Navigate to={identity.role === 'utility' ? '/utility' : '/building'} replace />
  }
  return <>{children}</>
}
