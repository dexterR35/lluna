# Desktop releases

Midgard publishes complete, hardware-specific desktop builds. Packaged users do
not need Python, Git, or `midgardEnv`; the selected runtime is frozen into the
release. Settings and downloaded models live in per-user directories and are
not replaced by application updates.

Python 3.12 is a build-time and source-install requirement. Release installers
must never download Python, run `pip`, or modify a user's system Python. The
frozen application validates its embedded 64-bit Python 3.12 runtime, packaged
resources, and writable user directories on first launch.

## Release targets

| Target | Package | Runtime profile |
| --- | --- | --- |
| Windows x64 | signed Inno Setup `.exe` | CPU, CUDA, or DirectML |
| Linux x64 | signed-manifest `.tar.gz` | CPU or CUDA |
| macOS Intel | signed/notarized `.dmg` | MPS |

## Installer experience and logs

- Windows uses the Inno Setup wizard's native progress display. It records the
  final setup log at `%LOCALAPPDATA%\Midgard\logs\installer.log`.
- Linux's `install-midgard.sh` shows copy and activation progress in the
  terminal and records `~/.local/state/midgard/installer.log` (or the equivalent
  `XDG_STATE_HOME` path).
- macOS uses Finder's copy progress when the user drags `Midgard.app` to
  Applications. The DMG includes a short Read Me.
- Every packaged platform appends first-launch dependency validation to
  `<config directory>/logs/install.log`.

The platform installer and first-launch validator both explain that Python is
embedded. Hardware-profile errors (for example, selecting CUDA without an
NVIDIA driver) must be actionable and must not silently install another build.

The current bundled macOS FFmpeg is x86-64. Do not label the DMG universal or
publish an ARM64 build until an ARM64 FFmpeg and every Python dependency are
verified and signed.

## One-time trust setup

Install packaging dependencies and generate the release-manifest key:

```shell
python -m pip install -r requirements-packaging.txt -c constraints.txt
python packaging/generate_update_key.py --private-output ../midgard-update-private.txt
```

1. Copy the printed public key into
   `backend/core/update_trust.py` as `UPDATE_PUBLIC_KEY_B64`.
2. Store the private file's single-line value in the protected GitHub release
   environment as `MIDGARD_UPDATE_PRIVATE_KEY_B64`.
3. Keep the private key offline as a recovery backup. Never commit it.

Rotating this key requires a release signed by the old key that ships the new
trust root. Losing the private key without a prepared rotation disables safe
automatic updates for existing installations.

## Required GitHub secrets

Windows:

- `WINDOWS_CERTIFICATE_BASE64`
- `WINDOWS_CERTIFICATE_PASSWORD`

macOS:

- `APPLE_CERTIFICATE_BASE64`
- `APPLE_CERTIFICATE_PASSWORD`
- `APPLE_SIGNING_IDENTITY`
- `APPLE_ID`
- `APPLE_TEAM_ID`
- `APPLE_APP_PASSWORD`

Shared:

- `MIDGARD_UPDATE_PRIVATE_KEY_B64`

Put these secrets in a protected `release` environment, require reviewer
approval, and restrict that environment to version tags. The workflow refuses
to publish a tag when the required platform certificate or manifest key is
missing.

## Publish

Keep all three version declarations equal:

- `backend/core/build_info.py`
- `pyproject.toml`
- README version badge

Then run the full tests, commit, push, and create the signed tag:

```shell
git status
python -m pytest -q
git tag -s v1.5.0 -m "Midgard 1.5.0"
git push origin main
git push origin v1.5.0
```

The tag starts `.github/workflows/desktop-build.yml`. It builds and tests each
target on its native OS, signs Windows and macOS outputs, notarizes the DMG,
creates a canonical Ed25519-signed update manifest, generates provenance
attestations, and uploads all assets to the GitHub Release.

## Update behavior

Packaged Midgard downloads `midgard-update.json` and its detached signature,
verifies the pinned Ed25519 key, selects the exact OS/architecture/profile,
streams the artifact into the per-user update directory, verifies size and
SHA-256, and only then starts the external installer.

- Windows uses the signed per-user installer.
- Linux stages the archive beside the current installation and retains the old
  directory for rollback.
- macOS verifies the staged app signature before swapping bundles and retains
  the old app for rollback.

Source checkouts remain notification-driven and use `git pull --ff-only` plus
`python install.py --yes`; binary update code never mutates a source checkout.

## Release gates

Do not publish if any of these checks fail:

- clean-machine launch on every target;
- Windows Authenticode verification;
- Apple `codesign`, notarization, and stapling verification;
- signed-manifest verification and deliberate tamper rejection;
- update from the previous public version with settings/models preserved;
- rollback test after a deliberately broken staged application;
- package size below GitHub's per-asset limit;
- model, FFmpeg, dependency license, digest, and provenance review.
