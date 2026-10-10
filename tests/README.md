# Siagnos Stage 4 tests

Oracle: the Stage 4 behavioral specification (return episodes), not the current code.

## Run

    # Python. DB tests need a THROWAWAY database; the suite creates and drops its own schema in it.
    pip install pytest "psycopg[binary]" pydantic fastapi httpx
    export SIAGNOS_TEST_DSN="postgresql://user:pass@localhost:5432/siagnos_test"
    export SIAGNOS_SCHEMA_FILE=src/database/database_schema_updated.sql   # default: src/database/schema.sql
    pytest
    pytest --runxfail          # show the known implementation defects as raw failures

    # Extension (Node 20+)
    cd tests/extension && npm install && npm test

Add `tests/extension/node_modules/` to `.gitignore`. Without SIAGNOS_TEST_DSN the DB tests skip.

The schema file may be a hand-written `.sql` or a raw `pg_dump`, including PowerShell's UTF-16 output.
The loader decodes by BOM, drops `\restrict`, header `SET`, `OWNER TO` and `set_config('search_path')`
lines, and rewrites `public.` to the private test schema, so a dump never touches the real `public`.

## Markers

| Marker | Meaning |
|---|---|
| `spec_mismatch` (strict xfail) | Asserts the spec; a known implementation defect fails it. Becomes a hard failure (XPASS) once fixed: delete the marker then. IDs: `BUG1`..`BUG4` in `tracker/helpers.py`. |
| `integration` | Needs PostgreSQL. |
| `concurrency` | Needs two simultaneous transactions. |

## Files

| File | Covers |
|---|---|
| `tracker/test_return_episodes.py` | 24h inclusive start, stays in_progress, resolves 24h after last activity, boundary event starts the new episode, exactly one `return_visits` per resolved episode, multiple episodes, cross-fic |
| `tracker/test_reread_and_continuation.py` | Resolution precedence, reread threshold at every size, unique positions, 30-day age boundary, one-shot, two-shot, continuation after provisional reread |
| `tracker/test_reread_threshold.py` | `reread_threshold` table, ceiling, cap, no minimum history, float safety |
| `tracker/test_chapter_jumps.py` | Destination is never consumed, unresolved events mutate nothing, bucket 1/2 credit, backward navigation |
| `tracker/test_confirmation_timestamps.py` | Original timestamp preserved; late confirmation cannot move time backwards |
| `tracker/test_chapter_events_regression.py` | Existing bucket rules, unresolved close, confirmation, monotonic `chapters_read` |
| `tracker/test_persistence.py` | New connections and simulated API restarts keep behaviour and episode state |
| `tracker/test_concurrency.py` | Two interleaved transactions on one fic |
| `tracker/test_schema_contract.py` | Exact columns, enum, single-active-episode index, cascade, ratings and sessions gone |
| `tracker/test_ingestion_gate.py`, `tracker/test_models.py` | Ingestion before writes, payload contract |
| `extension/*.test.mjs` | `content.js` and `background.js`, including Browser Back |
