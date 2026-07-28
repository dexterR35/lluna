# Stage 11 — Testing Strategy

Baseline: `main` at `c7aa179`.

## Current inventory

The repository has one test module, `tests/test_enhance_denoise.py`, with seven passing tests under the host Python. The project virtual environment has no `pytest`. There is no pytest configuration, network isolation, GUI suite, worker lifecycle suite, hardware/model fixtures, coverage gate, or installer/launcher test suite.

## Target layout

```text
tests/
  unit/ integration/ characterization/ gui/ inference/
  hardware/ models/ media/ installer/ performance/
  fixtures/ fakes/
```

Tests should be reorganized only as coverage grows; first add shared safety fixtures and focused modules.

## Safety contract

Standard tests:

- set an isolated app/config/cache/home root before importing Midgard;
- block socket connections and patch common HTTP clients;
- make model download entry points fail immediately;
- disable update checks and first-run seeding;
- run without GPU and use deterministic fake profiles;
- generate tiny media under pytest temp directories;
- never read or modify `config/config.json`, `config/hf_token`, bundled weights, user caches, or pending production downloads.

Network/GPU/model-download tests require explicit markers and opt-in environment flags.

## Markers

`unit`, `integration`, `gui`, `hardware`, `network`, `gpu`, `cuda`, `directml`, `mps`, `slow`, `model_download`, `installer`.

Unknown markers are errors. Default selection excludes `network`, `gpu`, `slow`, and `model_download`.

## Fixture and fake design

- immutable CPU, CUDA, DirectML, MPS, ONNX-CPU, and partial-failure `HardwareProfile`s;
- fake model registry/loader with load/unload counters and injected failures;
- fake downloader that emits chunks but never opens a socket;
- fake update client returning current/new/offline/malformed/rate-limited results;
- fake clock for watchdog/idle release;
- fake worker transport/process for handshake, crash, stale events, cancel, and shutdown;
- generated 2×2 images and short low-resolution video only where decoder tests require it;
- isolated settings snapshot and path resolver.

## Missing-test matrix

| Area | Unit | Integration/GUI |
|---|---|---|
| metadata/config/paths | precedence, validation, atomic recovery | import without Qt/user mutation |
| hardware | all mocked profiles/failures/cache | manual platform probes |
| model registry | manifest/schema/state/checksum | fake download/install/recovery |
| inference | protocol, state machine, cancel/watchdog | spawned fake worker |
| media | paths, invalid FPS/dimensions, workspace | tiny encode/decode if FFmpeg available |
| GUI | presenter/state/view-model | offscreen startup, navigation, shutdown |
| installer | Python/backend decision matrix | subprocess dry-run |
| launchers | static quoting/exit contract | OS matrix smoke |
| updates | semantic versions/channels/offline | mocked HTTP only |

## CI set

Ubuntu, Windows, macOS on Python 3.12: compile, Ruff, formatting, typing, unit tests, safe integration, offscreen GUI, installer decisions, launcher checks, Bandit, dependency audit. No production model download or external services.

## Coverage goals

- Core/config/hardware/protocol/policy: 90% branches.
- Download state, worker lifecycle, media ownership: 85% branches.
- UI controllers/presentation: 75%.
- Framework adapters and vendored model code: behavior smoke tests rather than artificial line coverage.
- Overall first milestone: 70%, increasing only after stable isolation.

## Quality gates

No test reads production config or opens network; no unregistered markers; deterministic retries; zero leaked child processes/temp artifacts; focused suite under 60 seconds on CPU; required tests on every extraction.

## Manual hardware set

Windows CUDA and DirectML (10/11 as supported), Linux CUDA/CPU, Apple Silicon MPS, Intel/AMD CPU, ORT provider variations, low/medium/high VRAM, driver mismatch, FFmpeg absent, shutdown during native inference.

## Files inspected

Existing tests, requirements, workflows, config/hardware/model/download/inference/media/GUI/installer and launcher code.

Recommended next stage: performance audit after the safety harness exists.
