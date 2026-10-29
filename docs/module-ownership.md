# Module ownership

```
frontend/**              → Sam
backend/api/**           → Oğuz   (integration owner; docs/*contracts*.md, backend/integration/**)
backend/agent/**         → Bejan
backend/generator/**     → Rana   (also the WebsiteSpec definition)
backend/storage/**       → Koray
backend/api/services/executor.py → Oğuz (the only code that writes generated files)
```

(Current Sprint 4 branches and shared-file rules: `docs/sprint4-contracts.md`.)

Rules of the road:

- Work on a branch per module (`feature/<module>`), review through small PRs.
- The integration owner reviews a PR for interface compatibility, runs the integration tests
  (`pytest`) and merges. If a module breaks the integration, its owner fixes it.
- Modules talk through the contracts in `docs/api-contracts.md`; nobody imports another module's
  internals, and nobody but `backend/storage/` writes SQL.
- `backend/agent/` never runs a shell command; it returns actions, and `backend/execution/` runs them.

## Sprint 2 storage wiring (integration)

- The API now runs on `backend/storage/sqlite_storage.py::SQLiteStorage`, which implements
  `StoragePort` with integer IDs, sessions and full execution records. The database file is
  `DATABASE_PATH` (default `data/app.db`); tests use a temp file per test.
- Schema changes are appended to `MIGRATIONS` (tracked with `PRAGMA user_version`).
- `backend/storage/` also still contains Koray's original helpers (string IDs, `description`
  tasks, `success` flag). They are not used by the API. Koray owns reconciling them with
  `SQLiteStorage` (keep one schema) and extending `tests/storage/`.
