# Node authoring

Node definitions live in `backend/graph/registry.py`; the renderer never maintains a competing catalog. Add a stable namespaced `schema_id`, typed inputs/outputs, validated parameter definitions, capability/model metadata, cache policy, and an adapter identifier. Port types live in `backend/graph/types.py`.

Implement adapters in `RunManager._run_node` or `_run_inference`. Heavy model work must route through `InferClient`; do not import ML runtimes into React or send pixel arrays through JSON. Inputs and outputs should be artifacts or small scalar values. Side-effect nodes must declare `side_effects=True` and normally use `cache_policy="none"`.

After changes run:

```bash
.venv/bin/python scripts/export_contracts.py
.venv/bin/python -m pytest -q tests/test_graph_contracts.py tests/test_graph_execution.py
npm run build
```

Schema changes require a version bump and explicit migration before old workflows can load.
