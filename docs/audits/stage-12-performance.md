# Stage 12 — Performance Audit

Baseline: `main` at `c7aa179`. No optimization is proposed without measurement.

## Likely cost centers

### Startup

`gui.py` imports all six pages before `QApplication` creation and constructs them synchronously in `_build_pages()` (`gui.py:35-61`). Those pages import Pillow/OpenCV/model helpers and build complex widgets. `backend.config` imports qfluentwidgets, loads disk config/translations, and mutates the environment. The window then starts the worker, probes health, recovers pending downloads, and schedules an update. Blank/frozen-window risk is therefore dominated by import and eager construction, not the event loop.

### Runtime

- model cold load and model switching;
- full-resolution image copies and RGBA/RGB conversions;
- video decode plus frame prefetch and Python-side batching;
- OCR and mask expansion;
- ProPainter/STTN temporal windows and OOM retries;
- multiprocessing path/control traffic (large pixels generally stay on disk, which is good);
- FFmpeg output and audio merge;
- retained framework caches/VRAM fragmentation;
- preview pixmap rebuilds and large-image scaling.

## Instrumentation

Add monotonic timing events at: process start, diagnostic/config/hardware, Qt, imports, shell/pages, worker spawn/handshake, first paint, deferred work, ready. For jobs: validate, queue wait, model ensure/load, preprocess, infer, postprocess, encode/save, cleanup.

Use:

- `python -X importtime` and import-linter snapshots;
- `cProfile`/py-spy for Python CPU;
- Scalene/tracemalloc/memray for allocation and growth;
- psutil for process tree/RSS;
- `torch.profiler` and CUDA allocated/reserved/peak;
- FFmpeg `-benchmark` output;
- Qt elapsed timers and first-paint event;
- repeated-run leak loops.

## Benchmark matrix

| Benchmark | Baseline metric | Initial target | Method/trade-off |
|---|---|---|---|
| cold GUI startup | measure process→first paint/ready | first paint <2 s, ready <5 s on reference CPU with no downloads | timestamps; lazy pages may defer first-use cost |
| warm startup | same | <1.5 s first paint | warmed filesystem |
| worker handshake | spawn→PONG | <2 s | fake and real CPU worker |
| Remove BG image | wall time, peak RSS/VRAM | no regression >10% | fixed image/model |
| x2 upscale | px/s, peak memory | baseline then +15% only after profiling | fixed test image |
| low-light | px/s, peak memory | no regression >10% | fixed input |
| 10 s 720p/1080p remove text | fps, encode/infer split | establish per-model targets | generated deterministic clip |
| generation supported sizes | cold/warm seconds, peak VRAM | no OOM at offered preset | fixed seed/prompt |
| model switch | unload/load time and residual VRAM | residual within 10% after 5 cycles | framework metrics |
| shutdown | click→process exit | <3 s normal, <8 s forced | process-tree assertion |

Every performance PR records hardware/software/input, median and dispersion across at least five warm iterations, peak memory, expected trade-off, and a threshold test where stable.

## Measurement-led recommendations

1. Display shell first, lazily construct feature pages; measure first-use penalty.
2. Detect hardware once and share an immutable snapshot.
3. Start worker after first paint and require a lightweight handshake.
4. Keep model cache bounded by policy and record load/unload/fragmentation.
5. Avoid repeated Pillow opens/color conversions; document image ownership.
6. Preserve frame prefetch but tune queue/batch sizes from RAM/VRAM and resolution.
7. Stream encode rather than retain whole videos; keep bounded OOM retry.
8. Sample progress/log events to avoid GUI/event-queue saturation.
9. Clean job workspaces and measure RSS/VRAM after cancellation and failure.

## Regression tests

Import boundary budget, startup timing event completeness, queue bound, deterministic policy results, no unbounded temp/RSS growth over repeated fake jobs, shutdown deadline, and optional benchmark thresholds on dedicated runners.

## Unknowns

No reliable performance claims can be made from this environment without downloading/using production models, which this audit intentionally did not do. DirectML and MPS profiles require their target systems.

## Files inspected

Startup, pages/components, inference process, model loaders/caches, video I/O, subtitle pipeline, image features, diagnostics, and downloads.

Recommended next stage: source installation and launcher audit.
