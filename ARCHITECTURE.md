# Architecture and current boundaries

## Shape

A modular monolith with a Next.js App Router frontend and a FastAPI/SQLAlchemy API. The web server rewrites same-origin `/api/*` requests to FastAPI. The API owns business validation and calculations; UI values are display-only. PostgreSQL is the deployment database. SQLite is intended for local development and fast tests, not concurrent retail production.

```text
Browser ── same-origin requests/cookies ──> Next.js (UI + API proxy)
                                              │
                                              └── FastAPI /api/*
                                                     │
                                                   SQLAlchemy
                                                     │
                                                PostgreSQL
```

## Current domains and boundaries

- `backend/app/models.py`: user, organization, membership, product, stock movement, sale, sale line and idempotency records.
- `backend/app/main.py`: HTTP schemas, authentication dependencies, tenant scoping and thin endpoint orchestration. It currently combines the first few workflows; extract domain services as additional modules are added.
- `backend/app/database.py`: SQLAlchemy engine/session setup.
- `backend/migrations`: versioned Alembic schema.
- `frontend/app/page.tsx`: workspace shell and first operational views. Keep adding domain screens as features become real; do not present disabled links as shipped functionality.

All tenant-owned reads/writes in this implementation are scoped by the signed session's organization and a live membership lookup. Client-supplied organization IDs are not used for authorization. An account can be a member of multiple organizations in the schema, but organization switching and invitations are not yet implemented.

## Data and transaction rules

- Currency values are `NUMERIC(14,2)` and quantities are `NUMERIC(14,3)` in the model; calculations use Python `Decimal`, not `float`.
- Use PostgreSQL for production monetary precision. SQLite's numeric affinity may serialize a value as a float and does not reproduce PostgreSQL locking semantics.
- Stock on hand is `SUM(stock_movements.quantity)` within a tenant/product scope. Receipts create positive rows; sales create negative rows. No route edits historical movements.
- Checkout calculates prices from the server's current product rows, checks aggregate duplicate line quantities, obtains product row locks on PostgreSQL, writes the sale, lines, stock movements and idempotency record in one transaction.
- Idempotency key scope is organization-wide, and a request fingerprint rejects reuse of the same key with a different cart/payment method. Clients should reuse the key when retrying a timed-out identical request.
- Cash sales are confirmed at checkout. Manual bank transfers are **pending**, and credit is **unpaid**. No card/mobile-money provider exists, so card payment is rejected.
- There is no journal ledger yet; dashboard confirmed sales are not an income statement, profit, cash balance or tax report.

## Migrations and operations

Use `alembic upgrade head` before running the API when `AUTO_CREATE_SCHEMA=false`. Alembic is authoritative for deployment. The API's create-all convenience mode is intended only for local use. Compose waits for a healthy database and runs the migration command in the API container before Uvicorn starts.

API health endpoint: `/health`. OpenAPI: `/docs` (disable or restrict docs as appropriate for a public production deployment). No worker/queue exists yet; do not claim asynchronous jobs are processed.

## Planned evolution

Add services/routes/tests by domain: organizations and branch scope; purchasing/goods receipts; customer/supplier records; sale returns/refunds; payment provider confirmation/webhook deduplication; accounting postings with balanced journal constraints; invoices/tax snapshots; outbox-based offline sync; reports and forecasting. Use explicit state transitions, tenant scoping, audit events, idempotency, and migration-backed schema changes in every domain. Keep AI optional and downstream of deterministic data services.
