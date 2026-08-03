# Workflow format

A workflow is JSON with `format: "midgard-workflow"` and `version: 1`. It contains project identity/timestamps, nodes, typed edges, optional groups, project settings, viewport, and metadata. Node instances persist only stable schema identity, position, label, parameters, and state flags; backend definitions are never copied into project files.

Edges store source/target node and port IDs. The backend rejects unknown nodes/ports, incompatible types, duplicate single-input connections, required input/parameter omissions, invalid ranges, dangling edges, and cycles. Integer outputs may safely connect to number inputs; other conversions require explicit nodes.

The authoritative JSON Schema is [workflow.schema.json](contracts/workflow.schema.json). Electron writes `*.midgard.json` through a temporary file and atomic rename. Autosave recovery is stored separately in the per-user application data directory.
