// Minimal typed fetch client for the Commonwatt API.
// Base URL comes from VITE_API_BASE_URL (see web/.env.example); defaults to
// the local FastAPI dev server started by `make serve`.

import { getSession } from './session'

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

// Identity headers the backend expects (X-User-Id / X-Role). The real BFF would
// set these from a session cookie; for the demo they come from the signed-in
// identity stored client-side. Absent when signed out.
function identityHeaders(): Record<string, string> {
  const session = getSession()
  if (!session) return {}
  const headers: Record<string, string> = { 'X-Role': session.apiRole }
  if (session.userId !== null) headers['X-User-Id'] = String(session.userId)
  return headers
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    // Spread init FIRST, then layer headers on top so caller headers and the
    // identity headers are never clobbered by `...init`. (Previously `...init`
    // came last and overwrote the headers, dropping Content-Type on POSTs.)
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...identityHeaders(),
      ...(init?.headers ?? {}),
    },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path)
}

export function apiPost<T>(path: string, body?: unknown, headers?: Record<string, string>): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}
