# BizFlow Africa

**Run Your Business. Understand Your Numbers. Grow Smarter.**

BizFlow Africa is an original, open-source-first business workspace for African SMEs. This repository began as an empty scaffold, so the current implementation deliberately establishes a tested foundation rather than claiming the entire master feature list is finished.

## What works today

- Account creation, sign-in/out, password hashing with Argon2id, signed 12-hour HTTP-only sessions, double-submit CSRF checks and organization membership validation.
- Organization-scoped product catalog with SKU uniqueness, categories, pricing and reorder thresholds.
- Ledger-derived inventory balances and append-only stock receipts.
- POS checkout with server-side price/stock validation, Decimal calculations, database transactions, product row locks on PostgreSQL, request idempotency and a persisted request fingerprint.
- Cash sales are marked paid; bank-transfer sales remain pending verification; credit sales remain unpaid. Card payment is intentionally unavailable until a real provider adapter exists.
- Database-backed overview with confirmed cash sales, recent transactions and low-stock alerts. Empty workspaces show empty states, not sample metrics.
- Responsive Next.js workspace, registration, catalog, inventory, POS and sales history.
- FastAPI OpenAPI docs, SQLAlchemy models, Alembic migrations, SQLite local mode and PostgreSQL deployment path.

## Not implemented yet

This is an early foundation, **not a complete accounting system or production-ready SaaS**. Multi-branch/warehouse operations, invitations, email verification and recovery, tax calculation, purchases/receiving, refunds, payment confirmation/webhooks, invoices, double-entry accounting, employee/payroll, offline/PWA sync, reports beyond the overview, AI/forecasting, file storage, audit-event coverage, subscriptions, platform administration, rate limiting and comprehensive browser E2E tests are not implemented. Do not use it as the sole financial record or for regulated accounting/tax workflows yet. See [PROGRESS.md](PROGRESS.md) for phase status.

## Run locally (SQLite development)

Requires Python 3.11+ and Node.js 22+.

```bash
# Terminal 1 — API
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — web app
cd frontend
npm ci
BIZFLOW_API_URL=http://127.0.0.1:8000 npm run dev
```

Open http://localhost:3000. The Next.js server proxies `/api/*` to FastAPI, so browser requests use same-origin URLs. API docs are at http://localhost:8000/docs. The local database defaults to `backend/bizflow.db`; it is ignored by Git. `SECRET_KEY` has a development-only fallback; set a unique random value for any shared environment. Set `COOKIE_SECURE=true` when served over HTTPS.

## Run with Docker Compose (PostgreSQL)

Requires Docker Engine and Compose. Create a local env file, set a long random secret, and keep the PostgreSQL password URL-safe (or percent-encode special characters in `DATABASE_URL`):

```bash
cp .env.example .env
# Edit .env; never commit it.
docker compose up --build
```

The API container applies Alembic migrations before serving. PostgreSQL data persists in the `postgres_data` volume. For an HTTPS reverse proxy, set `COOKIE_SECURE=true`, configure `CORS_ORIGINS` to the exact trusted web origin, use strong managed secrets, and terminate TLS at the proxy. Do not expose PostgreSQL publicly.

## Tests and checks

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest -q
PYTHONPATH=. .venv/bin/alembic upgrade head

cd ../frontend
npm ci
npm run lint
npm run typecheck
npm run build
npm audit --audit-level=high
```

The backend workflow tests use an isolated in-memory SQLite database. Use PostgreSQL for deployment and test database-specific concurrency/locking behavior before production.

## Configuration

| Variable | Purpose | Development default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy DB URL; use `postgresql+psycopg://...` in production | `sqlite:///./bizflow.db` |
| `SECRET_KEY` | Signs browser sessions; set a unique secret | Insecure local fallback only |
| `COOKIE_SECURE` | Set secure cookie flag behind HTTPS | `false` |
| `ENVIRONMENT` | `production` rejects the known development signing key | unset |
| `AUTO_CREATE_SCHEMA` | Local convenience table creation; production should migrate | `true` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:3000` |
| `BIZFLOW_API_URL` | Server-side Next rewrite target | `http://127.0.0.1:8000` |

See [.env.example](.env.example), [SECURITY.md](SECURITY.md), and [ARCHITECTURE.md](ARCHITECTURE.md).
