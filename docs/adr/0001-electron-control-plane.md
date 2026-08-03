# ADR 0001: Electron renderer with authenticated Python control plane

Status: accepted.

Midgard requires a graph editor while retaining mature local Python inference. Electron/React provides the graph and desktop surface; Python remains the domain and inference authority. The boundary is an authenticated ephemeral loopback API plus WebSocket events, with narrow native IPC only for OS actions.

This avoids embedding model runtimes in the renderer, prevents large binary IPC, preserves one-worker GPU scheduling, makes backend contracts independently testable, and removes the previous desktop toolkit dependency. Costs are two managed processes, contract/version discipline, and the need to package a Python sidecar.
