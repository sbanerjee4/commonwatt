// Client-side session for the cookie-auth backend (app/routes/auth.py).
//
// Login/logout/identity go through the real /auth endpoints. The session lives
// in an HttpOnly `cw_session` cookie set by the backend — JS never sees it — so
// requests just send `credentials: 'include'` (see lib/api.ts) and the browser
// attaches the cookie. We cache only the non-secret identity shape the SPA
// routes on, refreshed from /auth/me.

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

export type UiRole = 'utility' | 'facility'

// The identity shape /auth returns. Backend role is 'utility' | 'building_manager';
// we map it to the UI's 'utility' | 'facility' for routing/display.
export type Identity = {
  role: UiRole
  utilityId: string | null
  buildingId: string | null
}

type AuthResponse = {
  role: 'utility' | 'building_manager'
  utilityId: string | null
  buildingId: string | null
}

const STORAGE_KEY = 'commonwatt.identity'

function toUiRole(role: string): UiRole {
  return role === 'utility' ? 'utility' : 'facility'
}

function fromResponse(data: AuthResponse): Identity {
  return { role: toUiRole(data.role), utilityId: data.utilityId, buildingId: data.buildingId }
}

/** Cached identity for synchronous reads (routing/display). Null = signed out. */
export function getIdentity(): Identity | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Identity) : null
  } catch {
    return null
  }
}

function cache(identity: Identity | null): void {
  if (identity) localStorage.setItem(STORAGE_KEY, JSON.stringify(identity))
  else localStorage.removeItem(STORAGE_KEY)
}

/** Log in with real credentials. Throws on bad email/password (backend 401). */
export async function login(email: string, password: string): Promise<Identity> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    cache(null)
    throw new Error(res.status === 401 ? 'Invalid email or password.' : `Sign-in failed (${res.status}).`)
  }
  const identity = fromResponse((await res.json()) as AuthResponse)
  cache(identity)
  return identity
}

/** Clear the server session and local cache. */
export async function logout(): Promise<void> {
  try {
    await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' })
  } finally {
    cache(null)
  }
}

/** Re-read identity from the cookie via /auth/me. Returns null when signed out. */
export async function refreshIdentity(): Promise<Identity | null> {
  const res = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' })
  if (!res.ok) {
    cache(null)
    return null
  }
  const identity = fromResponse((await res.json()) as AuthResponse)
  cache(identity)
  return identity
}
