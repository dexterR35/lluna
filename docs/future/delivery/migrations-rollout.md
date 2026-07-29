# Migration and rollout

## Compatibility strategy

The editor engine is introduced beside existing pages. Compatibility adapters wrap
current functions as initial operation providers. A page migrates only after output,
cancellation, error, and CPU parity tests pass.

## Data migration

### Existing masks

1. Open the current NumPy archive read-only with pickle disabled.
2. Validate layer count, names, dimensions, dtypes, visibility, and protect flags.
3. Assign stable project mask/layer IDs.
4. Store raster tiles without altering values.
5. Record the import source/hash and conversion report.
6. Keep the original file untouched.

### Existing outputs

Outputs stay ordinary assets. Users may import them as source, comparison reference,
or project asset. Migration never deletes or replaces them.

### Settings

Map recognized settings to operation parameters or application preferences.
Unknown settings are preserved in a legacy namespace until a documented removal
version. Device preferences become policy hints; a saved CUDA preference does not
make a CPU-only machine fail.

## Application updates on another PC

Git history being current does not update an already installed Python application
by itself. The release system should:

- publish a signed version manifest and immutable release artifacts;
- check for updates at startup at most once per configured interval, never every
  second, and only when update checks are enabled;
- show version, release notes, size, and compatibility before download;
- download to staging, verify signature/hash, then install with rollback;
- migrate a copy of project/settings data on first launch;
- retain the prior runnable version until the new version starts successfully.

For source checkouts, provide an explicit updater command that fetches the selected
release/branch, updates a project-local virtual environment from a lockfile, runs
read-only preflight and migrations, then restarts. Never run an unattended `git
pull` over a dirty user checkout.

## Schema rollout

- Readers accept their current version plus explicitly tested older versions.
- Writers emit only the current version.
- Upgrade occurs on Save As or after a recoverable backup.
- Downgrade is read-only unless an explicit lossless exporter exists.
- Unknown operation nodes are round-tripped.

## Feature rollout

1. developer flag with fake/reference provider;
2. internal opt-in and golden/performance evidence;
3. beta opt-in with visible limitations;
4. default-on after crash, data-loss, and quality gates;
5. remove legacy path only after at least one stable release and migration evidence.

## Rollback

Feature rollback disables new execution but keeps documents readable. Model rollback
selects the prior fingerprint and preserves new results as assets. Application
rollback opens newer projects read-only if it cannot edit them safely.

## Failure scenarios

Test power loss during package replace, disk full during autosave/export, missing
linked media, missing/downgraded model, changed hardware, corrupted cache, truncated
journal, worker crash, encoder crash, and interrupted application update.
