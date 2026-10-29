# Operations: configuration, backup and integration status

## Environment

All application configuration is via environment variables listed in the root README and `.env.example`. Never commit `.env` or include secrets in support logs. A production deployment needs a managed secret store, strong unique signing key, HTTPS and secure cookies. PostgreSQL is the supported production DB. `AUTO_CREATE_SCHEMA=true` is a local convenience; production should use versioned migrations.

## Backups and restore

Compose persists PostgreSQL in the named `postgres_data` volume, but persistence is **not a backup**. No automatic backup schedule or restore verification is deployed by this repository. Operators must implement encrypted off-host backups, retention, access controls, and regular restore drills before production.

Example manual PostgreSQL backup and restore (run in a controlled environment; protect output files):

```bash
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > bizflow-$(date -u +%Y%m%dT%H%M%SZ).sql
# Restore only into an intentionally selected, empty/recoverable target database:
cat backup.sql | docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

The backup example is a manual operator command, not an automated or verified backup service. Test restores and application-level correctness before relying on a recovery-point objective.

## Payment integration

Only cash sales are confirmed by this implementation. Bank transfers are stored as pending until a future authorized reconciliation flow exists. Customer credit is unpaid. Card is rejected. No Paystack, Flutterwave, Stripe, payment link, webhook, refund or settlement adapter is configured. Do not mark redirects as proof of payment. A future adapter must keep provider secrets server-side, verify signed webhooks, deduplicate event IDs, reconcile asynchronous status and only post confirmed collections.

## Offline POS

Offline checkout and service-worker/IndexedDB synchronization are **not implemented**. The UI requires a reachable API for checkout and does not cache product/customer business data. Do not use this version as an offline POS, and do not queue locally confirmed card or transfer payments. Offline support must be designed with a visible outbox, client UUIDs, conflict handling, privacy controls on shared devices and server idempotency before being enabled.

## API

FastAPI generates the OpenAPI schema and Swagger UI at `/docs`; ReDoc is at `/redoc`. Use `/health` for liveness only; it does not currently verify PostgreSQL readiness or migration compatibility.
