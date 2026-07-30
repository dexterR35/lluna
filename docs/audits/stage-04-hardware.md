# Stage 04 — Hardware Detection Audit

**Audit date:** 2026-07-27  
**Scope:** `backend/tools/hardware_accelerator.py`, `backend/tools/system_info.py`,
`backend/tools/soft_defaults.py`, `backend/tools/vram_budget.py`, `install.py`,
`makedist.py`, FFmpeg resolution, and model-specific device selection.  
**Constraint:** audit and design only; no production code was changed.

## Executive assessment

Midgard does not yet have one hardware detector. It has several partial,
incompatible views:

- the installer recognizes only NVIDIA CUDA versus CPU;
- the runtime singleton recognizes Torch CUDA, an importable
  `torch_directml`, Torch MPS, and selected ONNX Runtime providers;
- the dashboard gathers a small, permanently cached display summary;
- soft-default selection invokes `nvidia-smi` again;
- model implementations independently decide whether CUDA, MPS, DirectML,
  ONNX, or CPU is acceptable.

The result is a high risk of reporting an accelerator that a selected feature
cannot use. The clearest example is DirectML: module discovery is treated as
availability, takes priority over a valid CUDA device, and is only tested when
the `device` property is later accessed. That property contains unreachable
code after `return` and a bare `except`.

The target should separate two concepts:

1. an immutable, evidence-bearing `HardwareProfile` describing what exists and
   what each framework successfully proved; and
2. an `ExecutionPolicy` describing what Midgard is allowed to use for a
   particular model, with an ordered and explainable fallback.

Hardware discovery must not select a model backend. Policy must not mutate the
hardware evidence.

### Import-time cost and side effects

Importing `backend.tools.hardware_accelerator` imports Torch immediately and
imports `backend.config` for translations. Torch's shared-library loading is a
material cold-start cost and can initialize framework-global state before the
application has validated configuration or chosen a policy. The singleton
defers its probes until `instance()`, but its first construction then prints
translated ONNX provider messages directly to standard output. Detection should
be explicitly invoked after logging/path/configuration setup; provider adapters
should import their frameworks lazily and report structured observations
instead of printing.

## Current detection paths

```text
install.py
  └─ nvidia-smi (up to three calls)
       ├─ first NVIDIA GPU name + compute capability
       ├─ first NVIDIA GPU total memory
       └─ banner "CUDA Version" (driver-supported API level)
            └─ choose CPU or CUDA wheel family
                 └─ write config/runtime.json

GUI / inference process
  └─ HardwareAccelerator.instance()
       ├─ find_spec("torch_directml")       [presence only]
       ├─ torch.cuda.is_available()
       ├─ torch.backends.mps.*
       └─ onnxruntime.get_available_providers()
            └─ mutable enabled flag + lazy device selection

Home dashboard
  └─ collect_system_info()                 [cached forever per process]
       ├─ OS / CPU / RAM platform calls
       └─ HardwareAccelerator.instance()

Soft defaults
  └─ independent nvidia-smi probe

Individual model
  └─ its own CUDA/MPS/general-device/ONNX/CPU branch
```

`config/runtime.json` is an installer note, not a trustworthy cache. It records
the selected install mode, Torch wheel tag, first GPU name, compute capability,
and total VRAM, but has no schema, hardware fingerprint, driver identity,
creation time, validation result, or invalidation rule.

## Field-by-field audit

### CPU

| Required field | Current source | Current quality | Required normalization |
|---|---|---|---|
| Vendor | Not collected | Missing | Stable enum (`INTEL`, `AMD`, `APPLE`, `ARM`, `OTHER`, `UNKNOWN`) plus raw string |
| Model | `platform.processor()`, then first Linux `/proc/cpuinfo` model | Partial; truncated for display | Preserve full raw model; create a separate display label |
| Architecture | Not explicitly collected | Missing | Normalize `platform.machine()` and Python bitness to `x86_64`, `arm64`, etc. |
| Physical cores | Not collected | Missing | OS-native/`psutil.cpu_count(logical=False)` with confidence |
| Logical threads | `os.cpu_count()` | Present but displayed as “cores” | Rename to logical threads and validate positive value |

The current dashboard can therefore tell a user that a 16-thread/8-core CPU
has “16 cores.” CPU feature flags, NUMA topology, efficiency/performance core
distinctions, and instruction sets are outside the requested minimum, but the
profile should allow optional extension without changing its schema.

### Memory

| Required field | Current source | Current quality |
|---|---|---|
| Total RAM | `/proc/meminfo`, `sysctl`, or `GlobalMemoryStatusEx` | Available on major platforms |
| Available RAM | Linux and Windows only | Missing on macOS |
| Swap total/free | Not collected | Missing |

The current functions return formatted strings rather than byte counts, losing
precision and preventing validation. MPS VRAM reporting incorrectly reuses
total system RAM and invents “free VRAM” as 50% of it. Unified memory should be
reported as unified memory with `available_vram_bytes=None`; policy can reserve
RAM explicitly.

### GPU

| Required field | Installer | Runtime | Gap |
|---|---|---|---|
| Vendor | NVIDIA implied | Not normalized | AMD, Intel, Apple and unknown vendors absent |
| Model | First `nvidia-smi` row | CUDA device 0 only; MPS generic | No multi-GPU inventory or stable identity |
| Total VRAM | First NVIDIA GPU | CUDA device 0; MPS uses total RAM | No DML/ORT values; MPS semantic error |
| Available VRAM | No | CUDA `mem_get_info`; fake MPS estimate | No process/device index or query timestamp |
| Driver version | Queried then discarded | No | Required field missing |
| CUDA driver/runtime | Banner API level only | No versions | Driver capability is confused with runtime/toolkit |
| Compute capability | `nvidia-smi`, first GPU | No | Not cross-checked against Torch |
| DirectML | No | `find_spec` only | Importable is not usable |
| MPS | No | Torch built + available | No allocation smoke test or reason |

The installer splits CSV rows on commas and selects only the first GPU.
`nvidia-smi`'s banner “CUDA Version” is the newest CUDA version supported by the
driver, not the installed CUDA toolkit and not necessarily the CUDA runtime
bundled in the chosen Torch wheel. The profile must carry these as distinct
fields:

- NVIDIA driver version;
- driver-supported CUDA API level;
- `torch.version.cuda`;
- ONNX Runtime CUDA provider build/version;
- Paddle CUDA build/version.

### Framework capability matrix

| Capability | Current test | What it actually proves | Required proof |
|---|---|---|---|
| Torch CUDA | `torch.cuda.is_available()` | Torch sees at least one CUDA device | Version, device list, allocation and tiny operation per candidate |
| Torch DirectML | `find_spec("torch_directml")` | Import resolution only | Import, enumerate/select device, allocate tensor, tiny operation |
| Torch MPS | `is_built() && is_available()` | Torch reports backend available | Allocation and tiny operation; record macOS/Torch versions |
| ONNX providers | `get_available_providers()` | Provider was registered | Create/run a tiny session per provider, record ordered failures |
| Paddle GPU | Not probed | Nothing | `paddle.is_compiled_with_cuda`, device count, selected device and tiny op |
| CPU fallback | Assumed | CPU device can be constructed | Import and tiny inference/operator checks by framework |

Provider enumeration is not execution validation. An ONNX provider can be
listed but fail to create a session because of missing DLLs, incompatible
driver/runtime libraries, or another provider's process-level conflict.

### System

| Required field | Current state |
|---|---|
| OS | `platform.system()` |
| OS version | Only `platform.release()` |
| Python architecture | Missing |
| Available disk space | Missing |
| FFmpeg availability | Not probed |

FFmpeg path resolution is embedded in `FFMPEGCLI`; construction can mutate
permissions with `chmod(0777)` and Windows construction can merge fragments.
This is not a capability probe. Detection should resolve the configured or
bundled executable, verify that it is executable, run `ffmpeg -version` with a
short timeout, and report version/path/source without altering the file.

## DirectML defect audit

The DirectML path in `backend/tools/hardware_accelerator.py` has four concrete
defects:

1. `check_directml_available()` assigns the `ModuleSpec` returned by
   `find_spec`, not a boolean and not a usable device result.
2. DirectML is checked before CUDA in `device` and `accelerator_name`. Merely
   installing `torch-directml` can divert a CUDA-capable machine to DirectML.
3. `self.__dml = True` follows the `return
   torch_directml.device(...)` statement and is unreachable.
4. `except:` catches `KeyboardInterrupt`, `SystemExit`, and every programming
   error, prints a traceback, mutates the singleton, and silently falls through
   to another backend.

There is also a documented process-level conflict between `torch-directml` and
some `onnxruntime-directml` versions. Current detection initializes ORT
provider discovery before the Torch DirectML device. It neither isolates nor
models that conflict.

Required behavior:

```text
discover module
  -> import with typed exception capture
  -> create candidate device
  -> run a bounded smoke test
  -> record AVAILABLE / UNAVAILABLE / BROKEN and evidence
  -> let per-feature policy choose it
```

Only expected runtime exceptions should become a negative capability result.
`BaseException` subclasses must propagate. Tracebacks belong in diagnostics;
the user-facing report gets a concise reason and remediation.

## Installer/runtime divergence

`install.py` offers `auto`, `cuda`, and `cpu`. It does not detect or provision
DirectML, MPS, ROCm, Intel/OpenVINO, CoreML, or Metal. `makedist.py` contains a
separate legacy DirectML packaging route and pins `torch_directml`, so packaged
and source installations can expose different hardware behavior.

CUDA provisioning is internally mixed:

- CUDA 11.8 selects CUDA Paddle, CUDA Torch, and a CUDA 11 ONNX Runtime feed;
- CUDA 12.6/12.8 selects CUDA Torch but CPU Paddle;
- Windows installs unpinned `onnxruntime-gpu`;
- CPU installs CPU Paddle, CPU Torch, and CPU ONNX Runtime.

Post-install verification imports packages but does not execute a tensor,
enumerate providers with expected results, or run Paddle on GPU. A successful
installation therefore does not prove the capability advertised by the
installer.

The target installer should consume the same detector schema (or serialize the
same evidence format), then install against an explicit requested policy. On
first application launch, the runtime must always validate the installed
frameworks; installer evidence may accelerate diagnostics but must never be
accepted as current truth.

## Model-specific execution decisions

| Feature/model | Current decision | CPU | CUDA | DirectML | MPS | ONNX providers | Finding |
|---|---|---:|---:|---:|---:|---:|---|
| STTN Auto | `HardwareAccelerator.device` | Yes | Yes | Yes | Yes | No | General device path; no model smoke test |
| STTN Detection | General device | Yes | Yes | Yes | Yes | No | Same |
| LaMa | Explicit CUDA, else MPS, else CPU | Yes | Yes | No | Yes | No | Ignores usable DirectML |
| ProPainter | CUDA if `has_cuda`, else CPU | Yes | Yes | No | No | No | MPS/DirectML excluded |
| PaddleOCR v5 | `device="cpu"` | Yes | No | No | No | No | HPI flag is not a GPU-device selection |
| rembg | Ordered ORT providers | Yes | Indirect | Indirect | Indirect | Yes | Provider registration mistaken for readiness |
| Real-ESRGAN | General Torch device | Yes | Yes | Yes | Yes | No | Compatibility is assumed |
| MIRNet | General Torch device | Yes | Yes | Yes | Yes | No | Compatibility is assumed |
| SAM2 + Grounding DINO | General Torch device | Yes | Yes | Yes | Yes | No | Pair VRAM estimate is coarse |
| FLUX.2 / Qwen-Image | Hard CUDA gate | No | Yes | No | No | No | Midgard explicitly requires CUDA and may offload model layers to CPU |

This matrix is the effective policy, but it is spread throughout implementation
code and can drift. A normalized policy table must be the sole place where
backend compatibility and preference are decided.

## Repeated probes and cache behavior

- Installer CUDA detection can run `nvidia-smi` three times.
- Soft defaults independently invoke `nvidia-smi`.
- Runtime imports Torch and probes CUDA, MPS, DirectML presence, and ORT.
- Dashboard calls the runtime singleton, then permanently caches its formatted
  result with `lru_cache(maxsize=1)`.
- Each inference worker is a separate process and creates its own singleton.
- CUDA free-memory queries are live, but static identity and provider results
  never refresh.

The permanent cache becomes stale after driver recovery, eGPU attach/detach,
hardware-acceleration preference changes, provider installation, or worker
restart. Conversely, repeated expensive imports/probes increase startup cost.

## Error handling and observability

### Silent or over-broad failures

- dashboard CPU/RAM/GPU functions broadly catch exceptions and display `-` or
  CPU without preserving structured reasons;
- CUDA VRAM errors become `(0, 0)`, indistinguishable from no GPU;
- DirectML uses bare `except`;
- ONNX initialization catches only `ModuleNotFoundError`; other import/provider
  failures can escape startup;
- MPS memory probing suppresses all failures;
- installer memory and banner queries suppress errors;
- Paddle HPI probing catches every `Exception` and silently disables it.

Detection should never make the application unusable because an optional
backend fails. It should, however, preserve every failure as a diagnostic
observation with source, exception class, safe message, and timestamp.

### Missing validation

- no positive/finite/range validation for memory and core counts;
- no correlation of Torch device index with `nvidia-smi` GPU identity;
- no multi-GPU selection or UUID/PCI identity;
- no 32-bit Python rejection;
- no disk-space threshold;
- no FFmpeg execution check;
- no framework/backend/model compatibility validation;
- no distinction between unavailable, untested, and broken.

## Target package

```text
backend/hardware/
  detector.py       # orchestration only; no model policy
  cpu.py            # CPU identity/topology observations
  memory.py         # RAM/swap observations
  gpu.py            # physical adapters and dynamic memory
  providers.py      # Torch/ORT/Paddle backend probes
  capabilities.py   # typed capability outcomes/evidence
  profile.py        # immutable normalized data model
  policy.py         # per-feature backend selection
  diagnostics.py    # redacted report and remediation
```

### Immutable `HardwareProfile`

Illustrative types:

```python
class Confidence(Enum):
    CONFIRMED = "confirmed"   # operation succeeded
    REPORTED = "reported"     # authoritative API reported it
    INFERRED = "inferred"     # derived from name/platform
    UNKNOWN = "unknown"

class CapabilityState(Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    BROKEN = "broken"
    UNTESTED = "untested"

@dataclass(frozen=True)
class Observation(Generic[T]):
    value: T | None
    confidence: Confidence
    source: str
    observed_at: datetime
    detail: str | None = None

@dataclass(frozen=True)
class GpuDevice:
    id: str                    # UUID/LUID/registry identifier where available
    vendor: str
    model: str
    total_vram_bytes: int | None
    available_vram_bytes: int | None
    unified_memory: bool
    driver_version: str | None
    cuda_driver_api: str | None
    compute_capability: tuple[int, int] | None

@dataclass(frozen=True)
class HardwareProfile:
    schema_version: int
    fingerprint: str
    captured_at: datetime
    os: OsProfile
    python: PythonProfile
    cpu: CpuProfile
    memory: MemoryProfile
    gpus: tuple[GpuDevice, ...]
    capabilities: FrameworkCapabilities
    disk: DiskProfile
    ffmpeg: FfmpegCapability
    observations: tuple[DiagnosticObservation, ...]
```

Raw facts use bytes and integers. Formatting is a presentation concern.
`available_vram_bytes` is a dynamic sample and may be absent; it must never be
fabricated. The profile may expose `static_view()` plus a separately timestamped
resource sample if callers need frequent free-memory updates.

### Separate `ExecutionPolicy`

```python
@dataclass(frozen=True)
class ExecutionPolicy:
    hardware_acceleration_enabled: bool
    preferred_backends: tuple[Backend, ...]
    selected_gpu_id: str | None
    allow_cpu_fallback: bool
    minimum_confidence: Confidence
    per_feature: Mapping[FeatureId, FeaturePolicy]
```

Resolution returns a decision, not merely a device:

```text
Decision(
  backend=TORCH_CUDA,
  device="cuda:1",
  dtype=FLOAT16,
  reason="confirmed smoke test; 10.4 GiB available",
  fallbacks=(TORCH_CPU,),
  rejected=(DIRECTML: "model unsupported", MPS: "not present")
)
```

Feature policy declares compatible backends, minimum RAM/VRAM, dtype support,
fallback permission, and whether a failed accelerator may retry on CPU. It
must not guess from a global `has_accelerator`.

## Detection orchestration

```text
Detector.detect(mode=QUICK)
  ├─ resolve OS/Python/disk/FFmpeg
  ├─ collect CPU and memory in parallel where safe
  ├─ enumerate physical GPUs with OS/vendor tools
  ├─ import optional framework adapters independently
  ├─ enumerate capabilities
  ├─ run bounded smoke tests required by configured features
  ├─ normalize and validate observations
  ├─ compute hardware/software fingerprint
  └─ return immutable HardwareProfile
```

`QUICK` may avoid expensive model-level tests but must still distinguish
reported from confirmed capabilities. `FULL` diagnostics runs all provider
smoke tests. Every external command gets an argv list, a short timeout, bounded
output, locale-stable parsing, and a captured result.

Recommended source preference:

- CPU/memory: OS APIs, with `psutil` only as a consistent adapter if made a
  required dependency;
- NVIDIA: NVML first, then `nvidia-smi`;
- Windows GPU: DXGI/PowerShell/CIM for identity and dedicated memory, then
  DirectML smoke test;
- macOS GPU/unified memory: system APIs/`system_profiler`, then MPS smoke test;
- Linux non-NVIDIA: sysfs/DRM plus framework/provider evidence;
- frameworks: their own version, enumeration, and execution APIs.

## Confidence policy

| Confidence | Meaning | May auto-select? |
|---|---|---|
| `CONFIRMED` | A representative bounded operation completed | Yes |
| `REPORTED` | Authoritative OS/framework API reports availability | Only when smoke test is intentionally deferred |
| `INFERRED` | Derived from a name, package, or heuristic | No; diagnostic/advisory only |
| `UNKNOWN` | No reliable evidence | No |

Package presence is `INFERRED`, provider enumeration is `REPORTED`, and a tiny
successful operation is `CONFIRMED`. A failed operation after positive
enumeration becomes `BROKEN`, not `UNAVAILABLE`.

## Cache and invalidation

Maintain two caches:

1. a disk cache of static identity and expensive successful probes; and
2. a process cache of the immutable profile plus live resource samples.

Cache key/fingerprint inputs:

- OS build and Python executable/architecture;
- GPU stable IDs and driver versions;
- versions/build metadata for Torch, `torch-directml`, ONNX Runtime, Paddle;
- Midgard hardware schema version;
- hardware-acceleration configuration;
- bundled FFmpeg path, size, and modification time.

Invalidate when any input changes, on explicit “Rescan hardware,” after a
provider smoke-test failure, after worker crash with a device error, and after a
bounded TTL (recommended 24 hours for static facts). Never persist available
RAM/VRAM. Refresh dynamic memory immediately before large allocation decisions.
Use an atomic replace and a process lock for the disk cache.

## Fallback behavior

1. Resolve policy for the specific feature.
2. Select only a compatible capability meeting the minimum confidence.
3. Re-sample memory and reject the candidate if the model budget cannot fit.
4. If initialization fails with a classified device/provider error, mark that
   capability broken for this process and try the next declared backend.
5. Retry on CPU only when the feature declares CPU compatibility and the user
   has not disabled CPU fallback.
6. Never retry CUDA OOM blindly on the same parameters. First unload/evict,
   lower an explicitly permitted tile/batch setting, or fail with guidance.
7. Never switch backend while a job is partly complete unless the operation is
   restart-safe.

Generate currently has no Midgard CPU fallback and should remain incompatible
in policy until it is deliberately implemented and tested. ProPainter should
similarly retain its observed CUDA/CPU matrix rather than inheriting a general
device automatically.

## Human-readable diagnostic report

The report should be copyable text and a structured JSON attachment:

```text
Midgard Hardware Report (schema 1)
Captured: 2026-07-27T12:34:56+03:00

System
  OS: Windows 11 24H2 (build ...)
  Python: CPython 3.12.8, 64-bit, x86_64
  Disk: 182.4 GiB available at <model root>
  FFmpeg: available, 7.1, bundled

CPU / Memory
  AMD Ryzen ... (AMD, x86_64), 8 physical / 16 logical
  RAM 32.0 GiB total / 21.4 GiB available
  Swap 8.0 GiB total / 8.0 GiB available

GPU 0
  NVIDIA ..., 12.0 GiB total / 10.4 GiB available
  Driver ..., CUDA driver API 12.8, compute capability 8.9

Frameworks
  Torch CUDA: CONFIRMED (Torch ..., runtime ...)
  Torch DirectML: UNAVAILABLE (package not installed)
  Torch MPS: UNAVAILABLE (not macOS)
  ONNX CUDA: BROKEN (missing cuDNN ..., fell back to CPU)
  Paddle GPU: UNAVAILABLE (CPU build)
  CPU: CONFIRMED

Selected policies
  STTN Auto -> Torch CUDA / float16
  PaddleOCR -> Paddle CPU / float32
  Generate -> Torch CUDA / bfloat16
```

Do not include usernames, tokens, full home paths, or environment values.
Report path values relative to application/user data roots where possible.

## Mocked test profiles

Tests should construct profiles without importing Torch or invoking system
commands:

- `cpu_only_8c16t_16g`: confirmed Torch/ORT/Paddle CPU;
- `nvidia_cuda_8g`: CUDA confirmed, ORT CUDA confirmed, Paddle CPU build;
- `nvidia_cuda_24g_multi_gpu`: two adapters and explicit selected ID;
- `directml_amd_8g`: DirectML confirmed, CUDA absent, ORT DML confirmed;
- `directml_package_broken`: package present but smoke test broken;
- `apple_mps_unified_16g`: MPS confirmed, unified memory, no fake VRAM;
- `onnx_openvino_only`: Torch CPU plus confirmed OpenVINO;
- `provider_listed_but_broken`: ORT advertises CUDA but session test fails;
- `low_disk`: otherwise valid accelerator with inadequate model disk space;
- `missing_ffmpeg`;
- `unknown_memory_values`;
- `driver_changed_cache_stale`.

For each profile, table-driven tests must assert feature decisions, fallback
reasons, dtype, minimum-memory handling, and diagnostic output. Adapter tests
mock subprocess/API outputs, including malformed/empty/multi-GPU
`nvidia-smi`, timeout, localized output, and permission failure.

## Migration plan

### Phase 1 — Capture current behavior

- Add characterization tests around the existing detector and every
  model-specific backend decision.
- Define backend IDs and the compatibility matrix exactly as observed above.
- Add fixtures for the mocked profiles.

### Phase 2 — Introduce normalized evidence

- Add `profile.py`, observation/confidence types, CPU/memory/system adapters,
  and diagnostic rendering.
- Keep `HardwareAccelerator` as a read-only compatibility facade.
- Stop returning formatted strings from the new core.

### Phase 3 — Framework probes

- Add independent Torch CUDA, Torch DirectML, MPS, ONNX, Paddle, and CPU probes.
- Fix DirectML by validating a device, removing unreachable code, and replacing
  the bare handler when implementation changes are authorized.
- Preserve optional dependency failures as structured observations.

### Phase 4 — Shared detection and caching

- Have installer and runtime emit/consume the same versioned profile shape.
- Add fingerprinted atomic cache and explicit invalidation.
- Remove duplicate `nvidia-smi` probing from soft defaults.

### Phase 5 — Execution policy

- Move each model's current compatibility rules into `policy.py` without
  expanding support.
- Replace global `has_accelerator` decisions feature by feature.
- Add live memory checks and explainable backend decisions.

### Phase 6 — Validate and expand

- Add actual backend smoke tests to install verification and diagnostics.
- Only then consider MPS/DirectML/ROCm/OpenVINO support for models that do not
  currently use them.
- Deprecate mutable singleton enablement after all consumers use policy
  snapshots.

## Acceptance criteria

- One immutable profile represents CPU, RAM/swap, every GPU, framework
  capability, disk, Python architecture, and FFmpeg.
- `AVAILABLE`, `BROKEN`, `UNAVAILABLE`, and `UNTESTED` are distinct.
- DirectML cannot outrank CUDA because a module merely exists.
- Installer, GUI, and worker agree on normalized backend identifiers.
- Every model receives an explicit, testable execution decision.
- Dynamic memory is never cached as static identity or fabricated.
- Optional-backend failure cannot prevent CPU-mode application startup.
- Diagnostics explain both the selected backend and every rejected candidate.
