# Security notes

## Implemented

- Passwords are hashed with Argon2id (`argon2-cffi`); no plaintext password is stored or returned.
- The browser session is a signed, HTTP-only, SameSite=Lax cookie with a 12-hour maximum age. Session payloads contain user/organization IDs only; the API checks the user, active status and current organization membership on each authenticated request.
- State-changing endpoints require a double-submit CSRF cookie/header pair. Login and registration are JSON-only exceptions; logout and business mutations require the token.
- Organization ownership is derived from the authenticated session and verified by tenant-scoped queries. Product IDs from another organization return not found.
- Financial and quantity inputs are validated server-side. Checkout totals and stock checks are server-authoritative.
- Production mode refuses the known development signing key. Secrets are not committed; `.env` is ignored.

## Deployment requirements and limitations

This is an early release and has not had an independent security review. Before production: configure a high-entropy secret, set `COOKIE_SECURE=true` behind HTTPS, use exact CORS origins, protect the API and OpenAPI docs as needed, use PostgreSQL on private networking, provision encrypted backups, patch and scan dependencies/images, add centralized rate limiting/WAF controls, monitor auth failures, and perform an external penetration review. No login rate limiter, email verification, password recovery, MFA, session revocation UI, role invitation workflow, security headers policy, file upload route, secrets manager, or full audit log is implemented yet.

The current `SameSite=Lax` cookie and CSRF header strategy assumes the web app and API are accessed through the same-origin Next.js proxy. Do not expose the API directly to browsers with broad CORS. The `SECRET_KEY` development fallback is unsafe for shared use; production mode blocks it, but operators must still supply a unique secret.

## Reporting

Do not report exploitable details in public issues. Contact the repository maintainers privately and include reproduction steps and impact. Never submit live credentials, business records, or customer personal data.
