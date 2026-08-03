# Local control-plane API

The API binds only to `127.0.0.1` on a per-launch ephemeral port. `/health` and `/ready` are public loopback readiness probes. All `/api/*` routes require the launch token in `X-Midgard-Token` or a Bearer header. `/api/events` requires the token during WebSocket connection.

Route groups cover version/capabilities, backend-owned nodes, workflow validation/compilation, runs and node previews, artifacts/thumbnails/metadata, settings/schema/reset, model lifecycle/download queue, path grants, diagnostics, and model release. Events use versioned envelopes with `eventId`, timestamp, type, optional `runId`/`nodeId`, and a small payload.

The generated contract is [openapi.json](contracts/openapi.json). Regenerate with `python scripts/export_contracts.py`.
