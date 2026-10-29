# Contributing

Thanks for helping build an original, open-source-first business platform. Please keep changes small, domain-focused and honest about incomplete functionality.

## Development

1. Create a feature branch from the current mainline (Arena-managed work should remain on its assigned branch).
2. Follow the local setup instructions in `README.md`.
3. Add an Alembic migration for every schema change; inspect generated migrations before using them.
4. Put business validation in typed backend schemas/services, scope every tenant query, and add a regression test for each invariant.
5. Do not put authoritative financial calculations in the browser or use binary floats for them.
6. Never commit secrets, live customer data, generated databases, build outputs or dependency directories.
7. Update docs and `PROGRESS.md` when behavior or phase status changes.

## Checks

```bash
cd backend && PYTHONPATH=. .venv/bin/pytest -q
cd frontend && npm run lint && npm run typecheck && npm run build
```

Use `npm audit --audit-level=high` for frontend dependency review. Tests should be deterministic, isolated, and must not be weakened merely to make a change pass. Current test coverage is a foundation only; add tests for permissions, tenant boundaries, failure paths and concurrency before expanding production claims.

## Pull requests

Describe user-visible behavior, schema changes, security implications, tests run and known limitations. Include screenshots for meaningful UI changes. Do not claim an external payment/AI/email service is connected unless a real adapter and verified sandbox flow are present.
