# Stage 16 — Future AI Infrastructure

Baseline: `main` at `c7aa179`.

## Principle

Stabilize the local desktop first. Midgard’s privacy and deployment advantage is local processing; a server, LLM, RAG, or agent layer is unjustified without a concrete media workflow.

## Horizon 1 — Local desktop stabilization

```text
PySide6 -> Local AI Gateway -> one-job Scheduler
        -> Model Manager -> Local Worker
        -> CUDA / DirectML / MPS / ONNX / CPU
```

Add typed jobs/status/errors, immutable hardware/config snapshots, verified manifests, bounded model cache, visible queue, cancellation acknowledgement, health/handshake, per-job workspaces, and measurable resource policy. Preserve the existing worker and GPU busy gate.

Framework policy:

- PyTorch/Diffusers remain for current pipelines.
- ONNX Runtime is appropriate for rembg and portable models when provider parity is tested.
- `torch.compile` is opt-in per model/backend only after warmup and cache measurements.
- TensorRT is a future NVIDIA expert optimization with build/cache/version cost; not a default.
- llama.cpp, Ollama, vLLM, embeddings, vector search, RAG, and agents are not added now because no validated Midgard workflow requires them.

## Horizon 2 — Multi-worker workstation

An optional advanced local mode may use one scheduler and multiple isolated workers by device/framework. It needs admission control, per-device memory reservations, priorities, cancellation, warm-model affinity, crash budgets, and result/workspace ownership. Default remains one GPU worker; CPU decode/encode may overlap only after profiling.

## Horizon 3 — Optional studio LAN

```text
Desktop clients -> mutually authenticated TLS gateway
                -> durable queue/scheduler
                -> GPU workers + versioned shared model store
                -> encrypted/expiring result store
```

Requirements: explicit enablement, authenticated users/devices, TLS, authorization by project, quotas, signed model manifests, content retention controls, audit events, secure discovery, resumable transfers, and no implicit internet exposure. Telemetry is opt-in and content-free.

## Cross-horizon contracts

- Versioned job/model/settings schemas.
- Model ID includes source revision and digest.
- Warm cache has RAM/VRAM budgets, LRU/priority eviction, and unload deadlines.
- Worker heartbeat/health differentiates slow load from crash.
- Cancellation states are requested/acknowledged/completed.
- Resource metrics are safe and local; prompts/media never enter telemetry.
- Results are atomically published; partials are quarantined and expired.

## Decision gates

Parallel workers require demonstrated queue demand and no memory safety regression. TensorRT/compile require repeatable speedup after build overhead. LAN mode requires a product owner, threat model, administration UX, and maintenance capacity. Generative language infrastructure requires a named user job, privacy case, and evaluation set.

## Risks

Framework/provider fragmentation, model license/gating, compiled-cache invalidation, GPU oversubscription, network privacy, and operational burden all exceed the value of premature expansion.

## Files inspected

Inference worker/client/protocol, hardware detection, feature frameworks, model managers/downloads, configuration, GUI busy gate, and roadmap audits.

Recommended next stage: production-readiness scoring.
