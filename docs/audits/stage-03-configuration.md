# Stage 3 — Configuration and Settings Architecture Audit

## Audit rules and snapshot

This report audits the configuration system at commit `c7aa179`
(`aupdate models`, 2026-07-27).

- Static inspection only; no configuration was loaded through an audit script,
  changed, migrated, or rewritten.
- The working copy's `config/config.json` is ignored runtime state, not a tracked
  shipped configuration. Its structure and types were reviewed without treating
  its user-specific values as product defaults.
- `config/hf_token`, if present, was not opened.
- Recommendations are incremental and preserve the public
  `backend.config` import surface during migration.

## Executive assessment

Midgard has one Qt-coupled global configuration object that also acts as a build
metadata module, repository metadata module, path registry, translation loader,
environment mutator, persistence layer, GUI signal source, and worker fallback.
It is convenient for widgets but unsuitable as the authoritative domain
configuration.

The current loader is permissive in the wrong places and brittle in others:
missing or invalid JSON silently becomes defaults; an invalid enum can terminate
the remainder of loading and leave a key-order-dependent partial state; most
integer and string fields accept any type; cross-field model constraints are not
validated; writes truncate the live file directly; and GUI and spawned worker
processes can address the same file.

There is no schema version, migration log, precedence model, shipped
configuration layer, environment override system, or immutable worker snapshot.
Some job settings are manually snapshotted, which correctly recognizes the
worker-staleness problem, but the snapshot is incomplete and unversioned.

The recommended target separates pure, typed domain models from Qt adapters and
introduces deterministic precedence:

```text
compiled defaults
  < shipped configuration
  < user configuration
  < environment variables
  < explicit runtime overrides
```

## 1. Current architecture

### Global module responsibilities

Importing `backend.config` currently:

1. suppresses qfluentwidgets promotional stdout during import;
2. imports Qt-backed `QConfig`, validators, serializers, and `Theme`;
3. defines build version and repository/update URLs;
4. defines hardcoded GUI sizes, behavior, durations, and rendering constants;
5. defines persistent runtime/model/hardware/UI settings as class-level Qt
   `ConfigItem` objects;
6. creates a process-global `Config`;
7. loads a relative JSON path into it;
8. forces qfluentwidgets dark theme in memory;
9. loads the English translation INI into a process-global `ConfigParser`;
10. defines `BASE_DIR` as the `backend/` directory;
11. overwrites `KMP_DUPLICATE_LIB_OK` in the process environment.

This module cannot be imported by a headless domain service or worker without
also importing PySide6/qfluentwidgets and taking these side effects.

### Current storage artifacts

| Artifact | Role | Tracking/path policy | Write behavior |
|---|---|---|---|
| `config/config.json` | Persistent functional settings | Ignored; path is relative to CWD | qfluentwidgets rewrites whole file directly |
| `midgard_runtime.json` | Installer hardware metadata plus soft-default marker | Ignored; repository-root absolute path | direct whole-file write |
| `config/pending_model_downloads.json` | Persistent transient download intent | Ignored; repository-root absolute path | direct whole-file write |
| `config/model_download_cancel.flag` | Cross-thread/process cancellation flag | repository-root absolute path | create/unlink |
| `config/hf_token` | Hugging Face secret | Ignored; repository-root absolute path | direct text write, best-effort mode `0600` |
| `backend/interface/en.ini` | Bundled English UI translations | Tracked resource-relative path | read-only |
| environment variables | Diagnostics, proxies, HF tokens, OpenMP workaround, native library settings | Process environment | read/mutated ad hoc |

The repository has no tracked `config/config.json`, shipped configuration
template, schema, or defaults document. Product defaults live in Python class
definitions and model-catalog modules.

### Current configuration inventory

#### Build and repository metadata

- `VERSION = "1.4.0"`
- project home, issues, releases, and update API URLs
- installer dependency versions exist separately in `install.py`
- README and Docker files duplicate version/package facts

The configured project URL is `midgard-app/midgard`, while the audited Git origin
documented by earlier stages is `dexterR35/midgard`. Regardless of which is
canonical, build/repository metadata has no single generated authority.

#### Hardcoded GUI and presentation values

Window/dialog sizes, navigation flags, Mica, timer durations, zoom limits,
checkerboard size, retouch history/overlay parameters, selection edge size, and
preview limits are plain class attributes. They are accessible through the same
`config` object but are not `ConfigItem`s and never participate in persistence,
validation, signals, or source precedence.

Theme is conceptually GUI preference but is forced to dark every import and
explicitly excluded from persistence via `_EPHEMERAL_CONFIG_GROUPS`.

#### Persistent runtime and model settings

- subtitle selection areas as one encoded string;
- inpaint and subtitle detector enums;
- background-remove, enhance, low-light, and generation selected modes;
- enabled model sets as comma-separated strings with sentinel `__none__`;
- enhance/low-light maximum dimensions;
- denoise flag and strength;
- generation width, height, and steps;
- object-selection complexity;
- inference watchdog, idle-release, and soft-default-applied flag;
- subtitle pixel tolerances and timeline counts;
- STTN and ProPainter batch/reference settings;
- hardware acceleration;
- startup update check;
- save directory.

`inferIdleReleaseSec` is configured but the current `InferClient` comments and
behavior keep models warm until explicit reset; the setting has no identified
consumer. That is configuration drift.

#### Secrets

HF tokens are correctly kept out of `config.json`, but the secret implementation
still has architectural issues:

- it accepts `HF_TOKEN` or `HUGGING_FACE_HUB_TOKEN`, then copies the resolved
  token into both names;
- a repository-local plaintext file is the fallback store;
- permissions are best-effort and Windows ACLs/keychains are not addressed;
- there is no token metadata, validation state, redacted diagnostic object, or
  explicit precedence declaration;
- the spawned child inherits the token-bearing environment.

#### Transient state

Pending downloads, cancellation, active jobs, selected task state, temporary
paths, process IDs, hardware discovery, and soft-default migration state are
split among ignored JSON, a flag file, singleton memory, and ordinary user
configuration. `SoftDefaultsApplied` is historical migration state stored beside
user preferences. `midgard_runtime.json` mixes installer facts with a duplicate
soft-default marker.

## 2. Loading, validation, and saving behavior

### Load

`CONFIG_FILE = 'config/config.json'` is resolved from the process working
directory. The generated launchers `cd` to the project root, masking the defect
for normal launch. Tests, module consumers, IDE configurations, and spawned
contexts need not do so.

qfluentwidgets opens JSON and uses `{}` on any open or parse exception. It then
walks JSON insertion order and deserializes known items:

- unknown groups and keys are ignored;
- missing keys retain compiled defaults;
- range values are clamped;
- enum values are constructed directly;
- generic `ConfigValidator` accepts any value and type;
- there is no top-level shape, schema version, or unknown-key report.

The entire method is wrapped in a decorator that catches `BaseException` and
returns `None`. An invalid enum or incompatible range type therefore ends the
load at that key, silently preserving already-loaded values and defaulting the
rest. This is neither fail-fast nor field-isolated recovery.

### Save

Every ordinary `config.set()` calls `qconfig.save()` immediately unless the new
value compares equal. Save:

1. creates the parent directory;
2. opens the live path with `"w"` (truncating it);
3. serializes the entire configuration with indentation.

There is no temporary file, flush/fsync, atomic replace, backup, file lock,
compare-and-swap, write coalescing, or merge with concurrent changes. A crash or
power loss can leave empty/partial JSON. Two processes race with last-writer-wins
whole-file replacement.

Startup soft-default calculation calls `config.set()` repeatedly, causing
multiple full writes for one logical migration. Model selection normalization
during page construction can also write before the window appears.

### Corrupt and invalid state

There is no quarantine or recovery report. Invalid JSON remains in place until a
later save destroys it. Valid-but-invalid fields produce partial load. Invalid
unknown values in comma-separated enabled-model strings are silently discarded
by model-specific parsers, but the original string remains stored. An empty
string means factory defaults while `__none__` means empty, an implicit
three-state encoding that is easy to break.

## 3. Qt coupling

`Config` inherits `QConfig`, each setting is a class-level `QObject`, and writes
and restart notifications flow through Qt signals. Consequences:

- configuration cannot be created as a simple independent instance;
- worker imports require Qt libraries even though inference has no GUI;
- class-level `ConfigItem` values are shared across `Config()` instances in one
  interpreter;
- test isolation requires module/process isolation;
- persistence semantics are embedded in UI setter calls;
- domain code imports GUI infrastructure to read values;
- validators are constrained to qfluentwidgets' simple correction model;
- restart notifications are generic and presentation-specific.

qfluentwidgets should become a view adapter over typed settings, not the storage
or domain model.

## 4. Translation configuration

Only `backend/interface/en.ini` is loaded. There is no locale setting, locale
discovery, translation precedence, resource manifest, fallback chain, placeholder
validation, or completeness check.

`ConfigParser(interpolation=None)` correctly avoids interpreting percent signs.
However:

- `tr.read()` does not raise for a missing file and its return value is ignored;
- callers frequently use `tr["Section"]["Key"]`, so missing content later raises
  during page construction;
- translation and application configuration are exposed from the same module;
- translations are mutable process-global state;
- workers import the full translation file only to format some diagnostic
  strings;
- user-facing literals still appear outside the catalog.

Translations belong under a dedicated i18n loader with immutable catalogs and
key-by-key English fallback.

## 5. Environment configuration

Current recognized or mutated environment settings include:

- `MIDGARD_DIAG`, `MIDGARD_DIAG_CLICKS`, `NO_COLOR`;
- `HF_TOKEN`, `HUGGING_FACE_HUB_TOKEN`;
- `http_proxy` (but not a deliberate normalized proxy model);
- `KMP_DUPLICATE_LIB_OK`, overwritten to `True`;
- `PYTORCH_CUDA_ALLOC_CONF`, mutated in the inference worker;
- unrelated MPI/Azure variables used by vendored training code;
- installer/build-specific `QPT_Action`.

There is no general environment-to-settings layer. In particular, users cannot
override config path, user data path, cache/model path, update policy, hardware
policy, model policy, locale, watchdog, or save directory through a documented,
typed prefix.

Environment mutation happens after many imports in the GUI and independently in
the worker. Native-library variables that must be set before importing Torch or
OpenMP are not controlled by a validated bootstrap phase.

## 6. Hardware and worker configuration

The stored hardware setting is a single Boolean. It does not represent:

- preferred backend (`auto`, `cpu`, `cuda`, `directml`, `mps`, ONNX provider);
- device index;
- allowed fallback;
- per-feature backend differences;
- detected versus requested state;
- driver/provider versions;
- memory policy;
- capability-test outcome.

`HardwareAccelerator` is mutable global runtime state. Features repeatedly call
`set_enabled()` from the stored preference, so one caller changes the global view
for all others.

The GUI passes the hardware Boolean to the inference process at spawn. Subtitle
jobs manually snapshot selected modes and batch parameters; other jobs pass
different ad hoc payload fields. `apply_subtitle_job_config()` mutates the
worker's global Qt config. There is no snapshot schema/version, hash,
compatibility check, or proof that every configuration dependency was included.

This creates two failure classes:

1. **staleness** — a long-lived worker retains values imported at spawn unless a
   job remembers to override them;
2. **concurrent persistence** — the worker's startup `config.set()` defaults to
   saving, so it can address the same file as the GUI.

Workers should receive immutable pure-data snapshots and must never load or save
GUI user configuration.

## 7. Specific architecture findings

### Hardcoded and duplicated values

- version and repository endpoints live in `backend.config`;
- README duplicates version;
- installer and Docker files duplicate framework versions;
- download URLs live across model catalogs;
- the four default rembg model IDs are duplicated in `install.py`,
  `first_run_downloads.py`, and config defaults/catalog policy;
- UI timings, geometry, and rendering policy are Python constants on `Config`;
- the English locale path is fixed;
- config, token, pending, runtime, model, and temp paths are resolved by different
  modules with different bases.

### Missing or weak validation

- generic numeric values allow strings, floats, negatives, booleans, or nulls;
- generate width/height/steps have no bounds or divisibility rules;
- enhance/low-light long-edge limits have no bounds or unit types;
- watchdog and idle seconds have no sensible range;
- save directory need not exist or be writable;
- subtitle selection strings have no load-time grammar/bounds validation;
- enabled model strings are not canonicalized at load;
- STTN's documented relation is not actually validated:
  `getSttnMaxLoadNum()` computes a derived maximum but stored invalid combinations
  remain;
- model choice is not validated against installation/hardware until individual
  pages or jobs;
- URL schemes/hosts and version syntax are not validated;
- token file ownership/permissions are not verified on read.

### Type and unit inconsistencies

- config items expose enum objects, strings, ints, bools, and encoded sets through
  one mutable API;
- `BASE_DIR` is a string pointing to `backend/`, while other roots are `Path`
  repository roots;
- VRAM is passed as MB floats and shown as GB; MPS uses half system RAM as “free”;
- time values mix `*Ms` class attributes and `*Sec` config items without typed
  duration objects;
- `previewMaxSide=0` means unlimited through a sentinel;
- empty enabled-model string means defaults, while `__none__` means none;
- `HARDWARE_ACCELERATION_OPTION` is build policy and
  `hardwareAcceleration` is user preference, but both are ordinary module values.

### Process and thread safety

- qfluentwidgets config writes are not atomic or locked;
- registry/runtime writes have the same issue;
- worker and GUI can load different moments of the same file;
- per-process locks do not protect multiple processes;
- QObjects/signals are not a worker-safe configuration transport;
- direct `config.set()` from UI actions persists immediately and can interleave
  with background callbacks;
- no revision counter allows detection of lost updates.

## 8. Target package structure

```text
backend/
  core/
    build_info.py
    paths.py
    environment.py
  config/
    models.py
    runtime.py
    hardware.py
    gui.py
    loader.py
    migrations.py
    secrets.py
  i18n/
    translations.py
```

### `backend/core/build_info.py`

Pure immutable build/repository metadata:

```python
@dataclass(frozen=True)
class BuildInfo:
    product: str
    version: Version
    repository_url: HttpUrl
    issues_url: HttpUrl
    releases_url: HttpUrl
    update_api_urls: tuple[HttpUrl, ...]
    build_commit: str | None
    build_channel: Literal["dev", "stable"]
```

Generate or validate this from one canonical project metadata source. It is not
user configuration and never appears in writable settings.

### `backend/core/paths.py`

Resolve and validate typed paths exactly once:

```python
@dataclass(frozen=True)
class AppPaths:
    install_root: Path
    resource_root: Path
    user_config_dir: Path
    user_config_file: Path
    user_data_dir: Path
    cache_dir: Path
    model_dir: Path
    temp_dir: Path
    log_dir: Path
    secrets_dir: Path
```

Use platform user directories by default, not the source checkout. Allow a
single documented portable-mode marker and test/runtime override. Never derive
configuration from CWD.

### `backend/core/environment.py`

Read the environment once into a typed `EnvironmentOverrides`; validate names,
types, ranges, and paths; record redacted provenance. Apply required native
environment mutations before importing Torch/OpenMP/Qt consumers and do not
overwrite an explicit caller value without policy.

### `backend/config/models.py`

Define the root immutable configuration and shared value objects. Dataclasses
plus explicit parsers are sufficient; Pydantic is optional and should not be
introduced unless dependency policy accepts it.

```python
@dataclass(frozen=True)
class AppConfig:
    schema_version: int
    runtime: RuntimeSettings
    hardware: HardwarePolicy
    gui: GuiPreferences
    models: ModelPolicy
```

Use types such as `Duration`, `PixelCount`, `ImageSize`, `SubtitleRegion`,
`ModelId`, `DirectoryPath`, and `NonEmptyTuple`, with JSON serialization isolated
from domain types.

### `backend/config/runtime.py`

Own watchdog/cancellation/update behavior and output policy. Historical flags
such as soft-default completion belong in migration metadata, not runtime
preferences. Active jobs, PIDs, and pending downloads do not belong in
`AppConfig`; use separately versioned service journals.

### `backend/config/hardware.py`

Separate requested policy from detected state:

```python
@dataclass(frozen=True)
class HardwarePolicy:
    backend: Literal["auto", "cpu", "cuda", "directml", "mps"]
    device_index: int | None
    allow_cpu_fallback: bool
    memory_fraction: float | None

@dataclass(frozen=True)
class HardwareSnapshot:
    selected_backend: str
    devices: tuple[DeviceCapability, ...]
    onnx_providers: tuple[str, ...]
    fingerprint: str
    warnings: tuple[str, ...]
```

Only policy persists. Detection is transient/cacheable runtime state.

### `backend/config/gui.py`

Own locale, theme, window state, navigation, preview/rendering, and UI durations.
Separate immutable product design constants from user preferences. Window
geometry may be persisted here if desired, with screen-bound validation.

### `backend/config/loader.py`

Implement layered loading, provenance, field-isolated diagnostics, canonical
serialization, and atomic persistence. It has no Qt imports.

### `backend/config/migrations.py`

Pure sequential functions from schema N to N+1. Each migration is deterministic,
idempotent when guarded by source version, and tested against fixtures.

### `backend/config/secrets.py`

Expose a narrow provider:

```python
class SecretStore(Protocol):
    def get(self, key: SecretKey) -> SecretValue | None: ...
    def set(self, key: SecretKey, value: SecretValue) -> None: ...
    def delete(self, key: SecretKey) -> None: ...
```

Prefer OS credential storage where available; allow a permissions-validated file
fallback for source/portable installs. Logs and reprs must redact values.

### `backend/i18n/translations.py`

Load immutable locale catalogs from resource paths. Validate placeholders and
required keys in CI. Runtime lookup falls back:

```text
selected locale key -> bundled English key -> visible diagnostic key token
```

Workers should receive message codes and parameters, not load GUI translations.

## 9. Required precedence and provenance

Apply layers in this exact order:

```text
compiled defaults
  < shipped configuration
  < user configuration
  < environment variables
  < explicit runtime overrides
```

### Layer definitions

1. **Compiled defaults** are typed constructors in source and must always produce
   valid configuration.
2. **Shipped configuration** is a tracked read-only resource for distribution or
   channel policy. It cannot contain secrets or machine/user state.
3. **User configuration** is the versioned file in the platform user config
   directory.
4. **Environment variables** are documented deployment/session overrides, e.g.
   `MIDGARD_HARDWARE__BACKEND=cpu` and
   `MIDGARD_RUNTIME__CHECK_UPDATES=false`.
5. **Explicit runtime overrides** are command/test/API values passed to the
   bootstrap. They are in memory unless an explicit save operation is requested.

For every final field retain:

```python
SettingValue(value=..., source=ConfigSource.USER, raw_key="models.enhance.mode")
```

Diagnostics can then explain a value without dumping secrets. Invalid higher
precedence input produces a validation issue and falls back to the next valid
lower value for that field; it must not discard unrelated settings.

Environment parsing rules:

- only the `MIDGARD_` namespace;
- `__` separates nested keys;
- strict canonical bool, integer, float, enum, duration, and path parsing;
- unknown variables warn in diagnostic mode;
- secret variables route to `SecretStore` resolution and never enter ordinary
  config serialization;
- environment overrides do not persist automatically.

## 10. Type-safe model and validation policy

Validation occurs in three passes:

1. **Structural** — JSON object, supported schema, known types and keys.
2. **Field** — enum membership, bounds, normalized paths/URLs/model IDs.
3. **Cross-field/policy** — relationships and environment/capability constraints.

Minimum rules include:

- durations positive and bounded; serialize in one unit, preferably milliseconds
  or ISO-style explicit values;
- image sizes positive, bounded, and model-compatible;
- subtitle regions parse into tuples of normalized coordinates with
  `0 <= min < max <= 1`;
- batch/reference settings satisfy model constraints;
- output directory exists or can be created and is writable;
- model enabled sets contain only catalog IDs and serialize as JSON arrays;
- selected model either belongs to the enabled set or produces a field-level
  correction issue;
- hardware backend and device index are coherent;
- update URLs are HTTPS and build version is valid;
- locale exists or resolves through fallback;
- zero/unlimited sentinels become explicit `None`;
- unknown keys are retained only in a migration quarantine, never silently
  treated as active configuration.

Validation issues should include stable code, JSON path, source layer, safe
received type/value summary, correction, and severity.

## 11. Atomic writes and concurrency

### Atomic writer

For user configuration:

1. serialize one canonical JSON document in memory;
2. create a temp file in the same directory with restrictive permissions;
3. write, flush, and `fsync` the file;
4. preserve the previous valid file as a bounded backup;
5. `os.replace()` temp over target;
6. best-effort `fsync` the directory;
7. emit one committed revision.

Never truncate the live file first. Clean abandoned temp files on startup by age
and naming convention.

### Write API

Use explicit transactions:

```python
with config_store.edit(expected_revision=snapshot.revision) as draft:
    draft.gui.theme = Theme.DARK
    draft.models.enhance.selected = ModelId("RealESRGAN_x2plus")
```

Validate and write once on commit. UI controls update an in-memory draft/store;
use short debounce for ordinary preferences and immediate transactions only for
critical intent. Avoid one full-file write per setter.

### Process policy

Preferred: only the GUI/bootstrap owner writes user configuration. Workers receive
snapshots and return events. Installer configuration migration should run while
the GUI is absent.

If multi-instance GUI is allowed, use an OS file lock plus revision
compare-and-swap and merge non-conflicting fields. Otherwise enforce a
single-instance lock. Atomic replacement alone prevents corruption but not lost
updates.

Download journals and runtime caches need their own atomic stores and locks; they
must not be folded into user preferences merely to reuse this writer.

## 12. Corrupt-file recovery

On user-config read:

1. read bytes with a size limit;
2. parse JSON and validate schema;
3. if valid, continue;
4. if invalid, copy/move it to
   `config.corrupt-<UTC timestamp>-<short hash>.json`;
5. try the most recent validated backup;
6. otherwise use shipped + compiled defaults;
7. write a fresh canonical user file only after bootstrap reaches a safe commit
   point;
8. show a non-blocking warning with backup path and validation summary.

For valid documents with bad fields, preserve the original backup, accept valid
fields independently, and report corrections. Do not let JSON key order affect
outcome. Secrets must never be placed into the corrupt-config diagnostic bundle.

## 13. Migration from current `config.json`

Introduce `schema_version = 1` as the first typed format. Migration is one-time,
but remains callable for old profiles.

### Discovery

When the new user config does not exist:

1. check the explicit `--config`/runtime override;
2. check the legacy repository-root `config/config.json`;
3. do not search arbitrary CWDs;
4. acquire a migration lock;
5. copy the legacy bytes to a timestamped backup before parsing.

### Mapping

| Legacy group/key | Target |
|---|---|
| `Main.InpaintMode`, `SubtitleDetectMode`, pixel/timeline fields, selection string | typed subtitle/model policy |
| `Main.HardwareAcceleration` | `hardware.backend` (`auto` when true, `cpu` when false) |
| `Main.CheckUpdateOnStartup` | `runtime.update_policy` |
| `Main.SaveDirectory` | typed output policy path |
| `BgRemove.*`, `Enhance.*`, `LowLight.*`, `Generate.*` | per-feature `ModelPolicy`; enabled strings become arrays |
| `SelectObject.MoreComplex` | select-object model preference |
| `Infer.JobWatchdogSec` | typed runtime duration |
| `Infer.IdleReleaseSec` | migrate only if behavior is implemented; otherwise preserve as deprecated metadata and warn |
| `Infer.SoftDefaultsApplied` | migration metadata, not user preference |
| `Sttn.*`, `ProPainter.*` | validated per-model execution policy |
| excluded/hardcoded UI attributes | compiled/shipped GUI design defaults; do not invent user values |

Unknown keys go into the migration report. They may be preserved in a namespaced
`legacy_unmapped` backup artifact, not the active model.

### Soft defaults

Fold current one-time VRAM tuning into migration:

- use the already-created hardware snapshot;
- apply policy only when the legacy field is absent, not by comparing against a
  magic factory value;
- write all derived values in one transaction;
- record migration ID and hardware fingerprint in migration metadata;
- never rerun due solely to a deleted Boolean.

### Completion

Atomically write the new file, reread and validate it, then record migration
success. Keep the legacy file unchanged for at least one release; do not delete
it automatically. On subsequent startup, the new schema is authoritative.

## 14. Compatibility facade for `backend.config`

Migration should not require a flag-day rewrite. Retain a facade with the current
names:

```python
# backend/config.py — transitional facade only
VERSION = build_info.version_string
PROJECT_HOME_URL = str(build_info.repository_url)
BASE_DIR = str(paths.resource_root / "backend")
config = QtConfigAdapter(config_store)
tr = TranslationFacade(translations)
```

`QtConfigAdapter` should:

- expose legacy attributes and `.value` for existing call sites;
- map `get/set` to typed fields;
- emit the legacy Qt signals on committed changes;
- serialize enums in the legacy form where callers require it;
- issue opt-in deprecation diagnostics;
- never load files, mutate environment, or construct the store at import time.

Bootstrap installs the active store/facade explicitly before creating pages.
Headless code imports typed modules directly. Move consumers in slices:

1. build info and paths;
2. translations;
3. model catalogs/services;
4. hardware and job payloads;
5. settings widgets;
6. remove facade after all imports are migrated.

## 15. Worker-safe configuration snapshots

Define one versioned, immutable, JSON-serializable job envelope:

```python
@dataclass(frozen=True)
class WorkerConfigSnapshot:
    protocol_version: int
    config_schema_version: int
    revision: int
    hardware: HardwarePolicy
    runtime: WorkerRuntimeSettings
    feature: FeatureJobSettings
    digest: str
```

Rules:

- construct from one validated GUI revision;
- include only fields the worker requires;
- no QObjects, Paths without serialization, translation catalogs, URLs unrelated
  to the job, or secrets;
- secrets use short-lived explicit credentials only for a download worker, not
  inference snapshots;
- child validates schema/protocol and acknowledges the digest in READY/job-start;
- snapshot is applied to job-local objects, never a mutable worker global config;
- settings changes affect the next job unless policy explicitly restarts the
  worker;
- diagnostics record revision/digest, never sensitive values;
- tests assert each job builder includes every declared dependency.

The hardware discovery snapshot is separate from policy. The worker may verify
the parent snapshot against its process-local backend, but it should report a
capability mismatch rather than silently choose another backend.

## 16. Incremental migration plan

### Phase 1 — Characterize

- Add fixture-based tests for missing, corrupt, partially invalid, unknown, and
  wrong-type legacy JSON.
- Record all current defaults and every consumer.
- Add write-count and concurrent-write tests.
- Mark unused settings such as `inferIdleReleaseSec`.

### Phase 2 — Pure core

- Add `build_info.py`, `paths.py`, and `environment.py`.
- Make bootstrap resolve paths and native environment before importing heavy
  dependencies.
- Keep legacy constants as aliases.

### Phase 3 — Typed loader

- Add typed models, precedence/provenance, validation, migrations, backups, and
  atomic store.
- Read legacy config but initially mirror writes to the legacy shape only if
  rollback requirements demand it; never allow two independent authorities.
- Move first-run soft defaults into migration.

### Phase 4 — Secrets and i18n

- Introduce `SecretStore`, migrate the plaintext token with user consent/policy,
  and retain file fallback for portable source installs.
- Add translation catalogs, English fallback, and CI completeness/placeholder
  tests.

### Phase 5 — Qt adapter

- Back existing settings controls with `QtConfigAdapter`.
- Coalesce UI writes into validated transactions.
- Move GUI-only preferences and restart semantics out of the domain model.

### Phase 6 — Services and workers

- Convert model, hardware, update, download, and inference services to dependency
  injection.
- Replace ad hoc job dictionaries with versioned snapshots.
- Prohibit worker access to the user config store.

### Phase 7 — Retire legacy state

- Stop reading repository-root legacy config after a documented compatibility
  window.
- Remove module import side effects and qfluentwidgets as the persistence engine.
- Consolidate pending-download/runtime journals under their own schemas.
- Delete the facade only after static import checks find no legacy consumers.

## 17. Acceptance criteria

The target configuration system is complete when:

- configuration can load and validate in a Python process with no Qt import;
- CWD has no effect on resolved files;
- every field has a type, unit, bounds, source, and serialization rule;
- one bad field cannot prevent unrelated fields from loading;
- writes are atomic, revisioned, and bounded to one owner;
- corrupt input is preserved and recoverable;
- schema migrations are deterministic and fixture-tested;
- secrets never enter ordinary settings, logs, worker snapshots, or backups;
- build metadata, repository metadata, paths, runtime settings, GUI preferences,
  model policy, hardware policy, secrets, and transient state have distinct
  owners;
- worker jobs use one versioned immutable configuration snapshot;
- environment and runtime override precedence is documented and testable;
- the legacy `backend.config` facade contains no loading or environment side
  effects and can eventually be removed.
