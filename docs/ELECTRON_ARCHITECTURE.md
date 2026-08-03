# Electron architecture

Electron owns the desktop lifecycle. Its main process reserves an ephemeral loopback port, creates a 48-byte random token, spawns `midgard-backend` with hidden-window semantics, streams backend stdout/stderr to the application log, polls `/ready`, and only then displays the renderer. Shutdown waits for the sidecar so Uvicorn can cancel runs, downloads, and the inference worker.

The renderer is untrusted relative to native capabilities. `nodeIntegration` is disabled; `contextIsolation`, sandboxing, and web security are enabled. The preload exposes workflow file actions, local file selectors/path grants, approved external link IDs, recovery, platform metadata, menu events, and OS progress. It never exposes arbitrary filesystem, shell, IPC, or URL operations.

HTTP commands and queries require `X-Midgard-Token`; WebSocket connects with the same launch token. The token is held in memory and never persisted. Health/readiness are the only unauthenticated endpoints. CORS accepts only local renderer origins. Full media bytes use authenticated artifact endpoints; graphs and events contain artifact IDs and metadata.

Packaged renderer responses use `script-src 'self'`. Development adds `unsafe-inline` only for the Vite React-refresh preamble; the meta document does not carry a second, conflicting policy. Development CORS accepts HTTP origins on `localhost` or `127.0.0.1` at any port because Vite may move away from its preferred port, while the random session token remains mandatory.

Python owns node definitions, validation, compilation, execution, artifacts, settings, model actions, and run events. `InferClient` remains a single persistent model worker, preserving same-type FIFO, cross-type busy rejection, progress, cancellation, watchdog, and recovery behavior.
