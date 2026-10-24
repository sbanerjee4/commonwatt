# Decisions log

| Time | Decision | Why | What we tried first |
| ---- | -------- | --- | ------------------- |
| Oct 24 | Cut Mongo and Supabase Auth; one Postgres with seeded users so judges can run from a clean clone | Simplify demo setup, single source of truth, faster iteration, real foreign keys for role boundary | Separate Mongo for state + Supabase managed auth |
