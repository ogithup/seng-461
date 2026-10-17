# Module ownership

```
frontend/**            → Rana
backend/api/**         → Oğuz   (also: integration owner, owns docs/api-contracts.md)
backend/agent/**       → Bejan
backend/execution/**   → Sam
backend/storage/**     → Koray
```

Rules of the road:

- Work on a branch per module (`feature/<module>`), review through small PRs.
- The integration owner reviews a PR for interface compatibility, runs the integration tests
  (`pytest`) and merges. If a module breaks the integration, its owner fixes it.
- Modules talk through the contracts in `docs/api-contracts.md`; nobody imports another module's
  internals, and nobody but `backend/storage/` writes SQL.
- `backend/agent/` never runs a shell command; it returns actions, and `backend/execution/` runs them.
