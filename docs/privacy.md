# Privacy

ctxproxy is local-first. It makes network connections only to the upstreams in
your config; there is no analytics, update check, or phone-home.

## What is stored

| Store | Contents | Default |
|---|---|---|
| SQLite (`ctxproxy.db`) | request metadata, usage, cost, transform reports, drift, findings, quarantine events | enabled |
| Blob directory | original bytes for changed/omitted blocks, and optional full request bodies | only when `capture_payloads != "off"` |
| License file | not used; ctxproxy is MIT open source | — |
| Logs | request IDs, provider/model, status, latency; never authorization or API keys | stderr |

`capture_payloads` values:

- `off` — no request bodies or blobs.
- `changed_blocks` — originals of blocks changed by a transform (default).
- `full` — the complete pre-transform request body.

Captured text is redacted for common secret patterns before storage. Redaction
is best-effort; do not enable full capture on machines you do not trust.

## Retention and purge

`telemetry.retention_days` defaults to 14. `ctxproxy purge --all` deletes
requests, sessions, reports, drift, findings, captures and blobs. The dashboard
Settings page shows whether capture is on.

## Dashboard security

- loopback bind by default; remote mode requires an admin token;
- Host allowlist (localhost/127.0.0.1/::1/configured host) against DNS rebinding;
- per-run admin token printed in the startup banner, set as an `HttpOnly;
  SameSite=Strict` cookie;
- CSRF token on all mutating admin requests;
- no CORS headers; all assets are vendored/local.

The admin token is not stored in config or logs. If it leaks, restart the proxy
to rotate it.

## Provider credentials

The proxy forwards the client's own `Authorization` / `x-api-key` /
`x-goog-api-key` headers. It does not read, log, or persist credential values.
`docs/client-setup.md` explains how to point each client at the proxy.
