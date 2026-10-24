// Client-side session/identity for the demo.
//
// There is no /auth/login endpoint yet, so sign-in selects one of the seeded
// demo accounts (db/seed.py) and we persist its identity to localStorage. The
// API client (lib/api.ts) reads this to attach X-User-Id / X-Role headers that
// the backend's header-based access checks expect.
//
// Two role vocabularies exist in the backend: the users table uses
// "utility" / "building_manager", while the route guards check
// "operator" / "building_manager" (and /event/draft wants "operator"). We store
// both: `role` for display/routing, `apiRole` for the header the endpoints read.

const STORAGE_KEY = 'commonwatt.session'

export type UiRole = 'utility' | 'facility'
export type ApiRole = 'operator' | 'building_manager'

export type Session = {
  /** Seeded users.id, sent as X-User-Id. */
  userId: number | null
  /** Role used for routing/display. */
  role: UiRole
  /** Role string the backend endpoints check, sent as X-Role. */
  apiRole: ApiRole
  /** Building the session is scoped to (users.building_id), or null for operators. */
  buildingId: string | null
  email: string
}

// The four seeded demo accounts. Ids match insertion order on a fresh seed
// (utility@demo=1, building1@demo=2, ...). See db/seed.py DEMO_ACCOUNTS.
export const DEMO_ACCOUNTS: Record<UiRole, Session> = {
  utility: {
    userId: 1,
    role: 'utility',
    apiRole: 'operator',
    buildingId: null,
    email: 'utility@demo',
  },
  facility: {
    userId: 2,
    role: 'facility',
    apiRole: 'building_manager',
    buildingId: 'PH-BLDG-1',
    email: 'building1@demo',
  },
}

export function getSession(): Session | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Session) : null
  } catch {
    return null
  }
}

export function signIn(role: UiRole): Session {
  const session = DEMO_ACCOUNTS[role]
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
  return session
}

export function signOut(): void {
  localStorage.removeItem(STORAGE_KEY)
}
