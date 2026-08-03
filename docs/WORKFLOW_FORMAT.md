# Workflow format

A workflow is JSON with `format: "midgard-workflow"` and `version: 1`. It contains project identity/timestamps, nodes, typed edges, optional flow groups, project settings, viewport, and metadata. Node instances persist only stable schema identity, position, label, parameters, appearance, and state flags; backend definitions are never copied into project files.

Node `appearance` values control editor-only card layout, accent, completed-artifact thumbnails, fit, aspect ratio, and preview effects; they do not change processing or cache keys. A node may also retain a `result` reference containing the IDs and completion time of its latest locally stored artifacts, allowing completed previews to survive project save/reopen. Artifact files remain in Midgard's local artifact store and a missing artifact is reported without invalidating the workflow.

A flow group records its member `nodeIds` and `startNodeIds`. The editor uses those start nodes to run each boxed branch independently from its selected start through every connected output. Flow membership follows new downstream connections automatically. At downstream merges, execution also includes side-branch prerequisites so every connected input has a runtime value.

Edges store source/target node and port IDs. The backend rejects unknown nodes/ports, incompatible types, duplicate single-input connections, required input/parameter omissions, invalid ranges, dangling edges, and cycles. Integer outputs may safely connect to number inputs; other conversions require explicit nodes.

The authoritative JSON Schema is [workflow.schema.json](contracts/workflow.schema.json). Electron writes `*.midgard.json` through a temporary file and atomic rename. Autosave recovery is stored separately in the per-user application data directory.
