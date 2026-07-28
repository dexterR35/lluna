# Stage 09 — Security Audit

Baseline: `main` at `c7aa179`.

## Threat model and boundaries

Assets are user media, outputs, Hugging Face credentials, model integrity, local execution, and update trust. Inputs cross these boundaries:

```text
untrusted media ──> OpenCV/Pillow/AV/FFmpeg/native decoders
internet ──> model/update downloaders ──> executable model formats/cache
user paths ──> output/temp/delete operations
GUI process <──pickle-backed multiprocessing──> trusted child worker
environment/config/token file ──> frameworks and HTTP clients
```

The primary attacker is a malicious media/model/archive/source download or local unprivileged process reading weakly protected secrets/temp files. The IPC channel is local and inherits trust from the parent, but Python multiprocessing serialization must not accept external endpoints.

## Findings

| ID | Sev. | Location | Evidence and remediation |
|---|---|---|---|
| SEC-001 | Critical | bundled `.pt/.pth` and downloaded Torch/Diffusers files | Pickle-capable model formats can execute code during deserialization. Pin source/revision, publish SHA-256 manifests, prefer `safetensors`/weights-only APIs, and verify before load. Existing split-file manifests are size-oriented, not a complete provenance chain. |
| SEC-002 | High | `config/hf_token`, `backend/tools/hf_auth.py` | A plaintext repository-tree token file is mixed with ordinary app state and exported to process environment. Move to OS credential storage where available, otherwise mode-0600 user data outside source; redact and never commit. |
| SEC-003 | High | model download helpers | Several downloads rely on upstream URLs/cache behavior without a mandatory checksum, expected size, license acceptance, or atomic promotion. Add signed/versioned manifests, disk preflight, `.partial`, hash verification, and atomic install. |
| SEC-004 | High | `backend/config.py:24-29` and update service | Canonical repository mismatch redirects update trust. Centralize `dexterR35/midgard`; verify HTTPS GitHub API/archive checksums and never execute downloaded binaries. |
| SEC-005 | High | bundled FFmpeg/model binaries | Large opaque binaries are committed without an SBOM/provenance attestation. Record upstream version/license/hash and scan releases. |
| SEC-006 | Medium | `backend/main.py:440,454` | FFmpeg commands sometimes use `shell=use_shell`. Even if current argument construction is controlled, path/media input raises injection risk on shell platforms. Always pass argument arrays with `shell=False`; context-manage handles. |
| SEC-007 | Medium | temp files across UI and pipeline | Predictable shared temp directories and retained artifacts can expose user media. Use per-job mode-0700 directories, random names, restrictive creation, cleanup/retention policy. |
| SEC-008 | Medium | deletion/uninstall/partial cleanup | Cleanup is spread across model helpers and accepts model IDs/paths indirectly. Resolve against allow-listed roots, reject symlinks/path traversal, never recursively delete an unresolved root. |
| SEC-009 | Medium | logs/raw exceptions | Network/filesystem/framework messages may include private paths, query parameters, proxies, or environment context. Central redaction and structured safe fields are required. |
| SEC-010 | Medium | dependency set | Broad/unpinned dependencies and no lock/SBOM make compromise and reproducibility difficult. Add constraints, hashes where practical, Dependabot/dependency review, `pip-audit`, CodeQL, Bandit, and secret scanning. |

## Secrets policy

- Never store tokens in `config.json`, logs, job payloads, crash bundles, or child command lines.
- Read credentials only at the network boundary; pass token explicitly where APIs support it rather than globally mutating `HF_TOKEN`.
- Display only “credential configured/not configured.”
- Redact URL user info, authorization headers, environment values, and paths outside approved app roots.

## Download/update policy

Every model artifact has immutable ID/version/source/license/gated flag/size/SHA-256. Download to a private `.partial`; stream hash and enforce size/disk limits; atomically rename; quarantine mismatches. Source updates remain notification-driven or verified source archives. Never overwrite running source or execute a downloaded binary.

## Tooling gates

- Ruff security-relevant rules and formatting;
- Bandit for first-party code, with reviewed exclusions for model loading;
- `pip-audit` against locked/constraint inputs;
- CodeQL Python, dependency review, secret scanning;
- Semgrep rules for `torch.load`, unsafe archives, `shell=True`, broad deletion;
- CycloneDX/SPDX SBOM and SHA-256 release manifest.

## Acceptance criteria

No committed credentials; canonical update origin; mandatory model verification for new downloads; atomic state/artifact writes; no shell interpolation; safe extraction/deletion; dependency and secret scans in CI; provenance recorded for bundled executables/models; security-sensitive failures are visible and fail closed.

## Files inspected

Token/auth, config, model download/load helpers, installer, update service, FFmpeg/media paths, bundled artifacts, requirements, workflows, and logging.

## Unknowns

Current token file permissions and contents were intentionally not read; dependency CVEs require a current locked environment scan; upstream model licenses and hashes require release-owner verification.

Recommended next stage: logging and error handling.
