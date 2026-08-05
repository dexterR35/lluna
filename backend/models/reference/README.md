# Model references

This package is the source of truth for model identity and compatibility. It
contains metadata and contracts only; it never downloads, imports, or loads
weights.

| Area | File | Responsibility |
| --- | --- | --- |
| Catalog | `catalog.py` | Built-in model IDs, names, sources, sizes, licenses, and backend limits |
| Metadata | `metadata.py` | Immutable model records, expected files, and lifecycle states |
| Manifest | `manifest.py` | User-model manifest format and safe parsing |
| Capabilities | `capabilities.py` | Reviewed task/input/output contracts |
| Validation | `validation.py` | Runtime validation of declared model controls |
| Runtimes | `runtimes.py` | Curated Python/runtime profiles and compatibility checks |
| Schema | `model-manifest.schema.json` | Machine-readable manifest schema |
| Platform guide | `PLATFORM.md` | Runtime/storage architecture and model safety policy |

Downloads and lifecycle actions belong in `backend/tools/installers/`; inference
belongs in `backend/tools/` runtime modules or `backend/ai/<model>/`.
