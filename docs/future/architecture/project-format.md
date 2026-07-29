# Non-destructive project format and recovery

## Container

Use `.midgard` as a ZIP64 package with a strict manifest. During editing, use an
expanded private working directory; save compacts it atomically to the user target.
Large source video may remain linked instead of embedded.

```text
project.midgard
  manifest.json
  document/graph.json
  document/versions.json
  assets/<sha256>.<ext>
  masks/<mask-id>/index.json
  masks/<mask-id>/tiles/<level>/<x>-<y>.png
  candidates/<operation-id>/<candidate-id>.<ext>
  previews/<revision-hash>/<profile>.<ext>
  thumbnails/<asset-id>/<frame>.webp
  recovery/checkpoints.json
```

Cache files are excluded. Generated previews are optional and invalidatable.

## Manifest essentials

- format and minimum reader version;
- project ID, created/modified timestamps;
- document head and version branches;
- source asset records: embedded/linked, hash, byte size, media probe;
- color/alpha/metadata descriptors;
- operation and model fingerprints;
- mask dimensions, roles, tile hashes;
- linked-file relocation hints without absolute-path trust;
- optional preview and checkpoint references.

The project stores model ID, exact artifact hash/revision, provider version,
parameters, seed, device policy, and result fingerprint. It does not require that
the same device be present to open or inspect a project.

## Source media policy

- Embedded assets are content-addressed and immutable.
- Linked assets record size, modification hint, strong hash, and relative search
  paths. A mismatch pauses rendering and asks for relink; it is never silently used.
- Source media, existing project data, and prior outputs are never removed by save.
- “Consolidate project” copies linked files only after disk-space validation.

## Atomic save

1. lock only the target project, not the entire application;
2. validate current in-memory schema;
3. write a sibling temporary package;
4. reopen and validate central directory, manifest, hashes, and referenced entries;
5. fsync file and parent directory where supported;
6. atomically replace the destination;
7. retain one recoverable previous snapshot according to user policy.

Autosave writes a project-scoped journal and periodic snapshot, never the primary
package in place.

## Recovery journal

Journal records are length-delimited, checksummed command envelopes:

```json
{
  "sequence": 184,
  "base_revision": "rev_...",
  "command": {"type": "mask.commit_tiles", "payload": {}},
  "asset_hashes": [],
  "checksum": "sha256"
}
```

On startup after an unclean close, replay stops at the first invalid/truncated
record, reports recovered sequence count, and opens a recovered copy. It never
overwrites the last clean project without confirmation.

## Mask import/export

- Import current `.npz` stacks using `allow_pickle=False`, validate dimensions and
  bounded layer count, assign stable IDs, and preserve names/visibility/protection.
- Export one grayscale PNG per layer or a composited mask; include sidecar JSON for
  role, source dimensions, and coordinate transform.
- PNG import requires an explicit fit policy: exact, scale, crop, or place.

## Package security

- Reject absolute paths, `..`, symlinks, duplicate normalized names, encrypted
  unknown entries, extreme compression ratios, and declared sizes over limits.
- Stream extraction and hash verification; never extract to a shared predictable
  directory.
- JSON has depth, string, collection, and total-size limits.
- No Python pickle, executable script, or automatic plugin loading is allowed.
- Unknown operations/assets are preserved as opaque bounded JSON/blobs.

## Migration

Every format migration is pure, version-to-version, backed up, fixture-tested, and
idempotent. An older app opens a newer project read-only when it cannot safely
preserve edits. See [Migration and rollout](../delivery/migrations-rollout.md).
