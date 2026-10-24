---
inclusion: always
---

# Stack and conventions

## Language and tooling
- **Frontend:** React 18 + TypeScript, Vite, React Router, TanStack Query, MapLibre GL JS
- **Backend:** FastAPI (Python 3.12) + SQLAlchemy ORM
- **Database:** Postgres (psycopg2 or asyncpg); SQLite via SQLAlchemy for local dev/test
- **Testing:** pytest (backend), Vitest + React Testing Library (frontend), Playwright (E2E)
- **Auth:** bcrypt for password hashing; HTTP-only session cookies

## Project layout
- Backend: `app/` (FastAPI routes), `db/` (SQLAlchemy models, migrations), `mcp/` (MCP tools)
- Frontend: `web/` (React app), `public/` (static assets)
- Seeded data: `fixtures/` (SQL dumps or Python seed scripts)
- Tests: `tests/` (backend + integration), `web/tests/` (frontend)

## Testing
- Keep every MCP tool deterministic and pure given its inputs
- Property-based tests in `tests/properties/` for dispatch math (Hypothesis)
- Frontend unit tests use mocked BFF responses (fixtures)
- E2E tests run against a live seeded Postgres + BFF

## Running
- `make setup` — create Postgres, seed demo users (3 accounts), run migrations
- `make test` — pytest + Vitest + Playwright
- `make demo` — start FastAPI on :8000, React dev server on :3000

## Database
- **`users`** (id, email, role, building_id FK, password_hash, created_at)
- **`buildings`** (id, address, zip, property_type, gross_area_sf, site_eui, per_electricity, lng, lat, simulated)
- **`events`** (id, window_label, target_mw, cap_pct, status, version, created_at)
- **`call_history`** (id, event_id, building_id, kw_requested, timestamp, simulated)
- **`replies`** (id, call_id, building_id, reply_value, timestamp, simulated)
- **`trace_steps`** (id, event_id, ts, kind, summary, plan_version, tool_name, rejected_by)
- **`audit_log`** (id, user_id, event_id, action, timestamp)

## Auth flow
- Three seeded demo users: operator (can see all), city office (can see all), facility_manager (scoped to building_id)
- `/auth/login` validates bcrypt hash, stores session in `sessions` table, sets HTTP-only cookie
- Role checks via FastAPI dependencies: `@app.get("/utility/...", dependencies=[Depends(require_operator)])`
- Demo credentials in README

## Provenance
- Every number in the response carries `source_id` or `{ value, source_id, basis }`
- Frontend refuses to render a number without source_id (AC-30)

## Geography
- Use zip-level aggregates as primary layer; building markers as drill-in
- All buildings geocoded to (lng, lat) points at ingest; null lngLat values surface in OrphanPanel

## Style
- Trace events logged to `trace_steps` table as rows: event_id, ts, kind, summary, tool_name, version
- Conventional Commits; never commit with failing tests
- TypeScript strict mode; Python type hints required
