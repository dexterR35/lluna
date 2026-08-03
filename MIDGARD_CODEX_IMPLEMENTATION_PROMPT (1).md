# Midgard Electron Node Editor Migration and Implementation Prompt for Codex

> Implementation tracking: [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md). Checked items are locally verified; unchecked items are explicit remaining gaps.

## Role

Act as a principal-level desktop application engineer, senior React/Electron engineer, senior Python systems engineer, and AI media-pipeline architect.

You are working directly in the GitHub repository:

```text
https://github.com/dexterR35/midgard
```

Your job is to transform Midgard from its current PySide6/qfluentwidgets page-based desktop interface into a production-quality Electron desktop application with a chaiNNer-style visual node editor, while retaining and adapting the existing Python 3.12 AI-processing backend.

This is an implementation task, not a design-only exercise. Inspect the repository, modify the code, add tests, run validation, and leave the repository in a working state.

---

# 1. Product Objective

Build a new Midgard desktop application with this final architecture:

```text
Electron desktop shell
└── React + JavaScript/JSX renderer
    ├── @xyflow/react workflow canvas
    ├── Tailwind CSS
    ├── Custom Midgard UI components
    ├── Workflow/project management
    ├── Node inspector and previews
    ├── Settings and model management
    └── Run, pause, resume, stop, progress and logs
             │
             │ Authenticated loopback HTTP + WebSocket
             ▼
Python 3.12 control plane
├── Workflow validation and compilation
├── Job and artifact orchestration
├── Existing InferClient and inference worker
├── Existing AI models and processing code
├── Settings and model management
└── Durable project/run state
```

The final application must have:

- Electron as the only desktop GUI.
- React written in plain JavaScript and JSX, not TypeScript.
- `@xyflow/react` as the visual node-canvas library.
- Tailwind CSS as the only UI styling framework.
- Custom-built Midgard components instead of Chakra UI, MUI, Mantine, shadcn/ui, Radix UI, Bootstrap, Ant Design, or another component framework.
- The existing Python AI-processing implementation retained wherever practical.
- No PySide6, Qt, or qfluentwidgets dependency in the final repository or packaged application.
- No browser window, terminal window, or separately launched Python application visible to normal users.
- Fully local processing. Media must not be sent to a cloud service.

The design may be inspired by chaiNNer's workflow interaction model, but it must be an independent implementation. Do not copy chaiNNer source code, branding, icons, artwork, layouts, text, or GPL-licensed implementation details into Midgard. Recreate behaviors from first principles using Midgard-owned code and permissively licensed dependencies.

---

# 2. Current Repository Facts to Preserve

Before editing, inspect the current repository and verify these paths and responsibilities. Do not assume this prompt is more current than the repository.

Important current files include:

```text
midgard.py
backend/application/bootstrap.py
backend/config.py
backend/tools/infer_client.py
backend/tools/infer_protocol.py
backend/tools/infer_worker.py
gui.py
ui/
requirements.txt
pyproject.toml
install.py
install.bat
install.sh
run_gui.bat
run_gui.sh
.github/workflows/
```

The existing product currently provides local AI tools for:

- Image generation through Diffusers-based models.
- Text and subtitle removal from images and videos.
- Background removal.
- Image upscaling through Real-ESRGAN models.
- Low-light restoration through MIRNet.
- Object-assisted selection through SAM2 and Grounding DINO.
- LaMa retouch/inpainting.
- Model installation, enabling, disabling, removal and queued downloads.

The current inference design has valuable behavior that must be preserved or improved:

- One persistent shared inference worker.
- One GPU-heavy job at a time.
- Same-job-type FIFO queueing.
- Cross-tool busy protection.
- Progress callbacks.
- Log callbacks.
- Preview callbacks.
- Result and error callbacks.
- Soft and hard cancellation.
- Worker watchdog and crash recovery.
- Model release/reset behavior.
- Payloads based on file paths rather than huge pixel arrays.

Do not rewrite working AI algorithms merely to make the frontend migration easier. Create stable adapters around them.

---

# 3. Non-Negotiable Technology Decisions

## 3.1 Frontend

Use:

```text
Electron
Electron Forge with Vite integration
React
JavaScript and JSX
@xyflow/react
Tailwind CSS
Zustand or a small custom store for application/editor state
TanStack Query or a small custom API cache for server state
Vitest
React Testing Library
Playwright for Electron end-to-end tests
```

Use `.js` and `.jsx` source files. Do not introduce `.ts` or `.tsx` application source files.

Enable strong JavaScript checking through JSDoc and `checkJs`:

```json
{
  "compilerOptions": {
    "allowJs": true,
    "checkJs": true,
    "jsx": "react-jsx",
    "strict": true
  }
}
```

Use runtime schema validation for all process and network boundaries. Use JSON Schema, Pydantic-generated schema, or Zod only for validation; Zod is not a UI framework.

## 3.2 Styling

Use Tailwind CSS only for styling.

Do not install or use:

- Chakra UI
- MUI
- Mantine
- shadcn/ui
- Radix UI
- Bootstrap
- Ant Design
- PrimeReact
- Fluent UI
- Styled Components
- Emotion

Build reusable Midgard components in the repository.

An icon-only package such as `lucide-react` is acceptable, but icons must be bundled locally and must not require a network connection at runtime. Custom SVG icons are also acceptable.

## 3.3 Backend

Use Python 3.12.

Add a local control-plane API using FastAPI and Uvicorn unless repository inspection reveals a stronger existing non-Qt server foundation. Bind only to `127.0.0.1` on an ephemeral port.

The Python control plane must not import Electron, React, browser APIs, PySide6, Qt, or qfluentwidgets.

The Electron renderer must not import Torch, Diffusers, PaddleOCR, ONNX Runtime, OpenCV model code, or other ML runtimes.

## 3.4 Communication

Use:

- Authenticated loopback HTTP for commands and queries.
- WebSocket for run events, progress, previews, download progress and logs.
- Artifact IDs and file paths for media transfer.
- Narrow Electron IPC for native desktop actions only.

Do not send full-resolution images, frame arrays, model tensors, or large binary buffers through JSON, IPC or WebSocket messages.

---

# 4. Final Repository Structure

Create or converge toward this structure while respecting useful existing modules:

```text
midgard/
├── frontend/
│   ├── electron/
│   │   ├── main.js
│   │   ├── preload.js
│   │   ├── python-process.js
│   │   ├── native-menu.js
│   │   ├── window-state.js
│   │   └── security.js
│   ├── src/
│   │   ├── app/
│   │   ├── api/
│   │   ├── components/
│   │   ├── editor/
│   │   ├── nodes/
│   │   ├── workflow/
│   │   ├── inspector/
│   │   ├── preview/
│   │   ├── retouch/
│   │   ├── settings/
│   │   ├── models/
│   │   ├── downloads/
│   │   ├── diagnostics/
│   │   ├── state/
│   │   ├── styles/
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── tests/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── jsconfig.json
├── backend/
│   ├── api/
│   │   ├── app.py
│   │   ├── auth.py
│   │   ├── dependencies.py
│   │   ├── events.py
│   │   ├── routes_health.py
│   │   ├── routes_nodes.py
│   │   ├── routes_workflows.py
│   │   ├── routes_runs.py
│   │   ├── routes_artifacts.py
│   │   ├── routes_settings.py
│   │   ├── routes_models.py
│   │   └── routes_diagnostics.py
│   ├── graph/
│   │   ├── schema.py
│   │   ├── registry.py
│   │   ├── types.py
│   │   ├── validation.py
│   │   ├── compiler.py
│   │   ├── executor.py
│   │   ├── cache.py
│   │   └── migrations.py
│   ├── projects/
│   │   ├── schema.py
│   │   ├── repository.py
│   │   ├── autosave.py
│   │   └── recovery.py
│   ├── artifacts/
│   │   ├── models.py
│   │   ├── store.py
│   │   ├── hashing.py
│   │   └── cleanup.py
│   ├── configuration/
│   │   ├── schema.py
│   │   ├── service.py
│   │   ├── migration.py
│   │   └── defaults.py
│   ├── application/
│   ├── media/
│   ├── tools/
│   ├── inpaint/
│   └── existing model modules
├── contracts/
│   ├── node.schema.json
│   ├── workflow.schema.json
│   ├── event.schema.json
│   ├── settings.schema.json
│   └── openapi.json
├── tests/
├── docs/
│   ├── ELECTRON_ARCHITECTURE.md
│   ├── NODE_AUTHORING.md
│   ├── WORKFLOW_FORMAT.md
│   ├── API.md
│   ├── SETTINGS_MIGRATION.md
│   └── RELEASE_PACKAGING.md
└── package.json or root task runner configuration
```

Do not mechanically move every existing Python module. Preserve stable paths where changing them would create unnecessary risk.

---

# 5. Electron Desktop Requirements

## 5.1 Main process

The Electron main process must:

- Start the Python control plane automatically.
- Select an available loopback port.
- Generate a cryptographically random session token.
- Pass the port, token and application data paths through environment variables or protected startup arguments.
- Wait for `/health` before opening the main window.
- Show a proper startup error window when the backend cannot start.
- Capture Python stdout and stderr into Midgard log files.
- Restart the backend only when safe and intentional.
- Shut down the backend and inference worker cleanly when Electron exits.
- Prevent duplicate application instances unless multi-instance support is deliberately implemented.
- Support opening workflow files from the OS.
- Manage recent files.
- Provide native file and directory dialogs.
- Integrate progress into the operating-system taskbar or dock where supported.
- Prevent system sleep while an active workflow is running.
- Open external links through the system browser after validating the URL.

## 5.2 BrowserWindow security

Use secure defaults:

```js
webPreferences: {
  preload: preloadPath,
  nodeIntegration: false,
  contextIsolation: true,
  sandbox: true,
  webSecurity: true
}
```

Also implement:

- A strict Content Security Policy.
- No `eval` or remote code execution.
- No remote web content in the renderer.
- Navigation blocking.
- New-window blocking except for validated external links.
- Minimal `contextBridge` APIs.
- Explicit IPC channel allowlists.
- No generic `invoke(channel, ...args)` bridge.
- No unrestricted filesystem access in the renderer.

## 5.3 Preload bridge

Expose only narrow operations such as:

```js
window.midgardDesktop.openWorkflow()
window.midgardDesktop.saveWorkflowAs()
window.midgardDesktop.selectImageFiles()
window.midgardDesktop.selectVideoFiles()
window.midgardDesktop.selectDirectory()
window.midgardDesktop.revealPath(pathGrantId)
window.midgardDesktop.openExternal(urlId)
window.midgardDesktop.getPlatformInfo()
window.midgardDesktop.onMenuCommand(callback)
```

Do not expose Node's `fs`, `child_process`, `process`, `shell`, arbitrary paths, or arbitrary IPC.

---

# 6. Python Control Plane Requirements

## 6.1 Startup

Replace the Qt-specific desktop bootstrap with a backend-service entry point.

The control plane must:

- Validate Python 3.12.
- Initialize logging and application paths.
- Validate packaged resources.
- Load functional settings without Qt.
- Apply Hugging Face credentials where configured.
- Apply hardware defaults.
- Clean stale workspaces.
- Start or lazily start `InferClient`.
- Expose health and readiness separately.
- Emit structured startup errors.

Create a backend command similar to:

```text
python -m backend.api.app --host 127.0.0.1 --port <port> --token <token>
```

## 6.2 API surface

Implement at minimum:

```text
GET    /health
GET    /ready
GET    /api/version
GET    /api/capabilities
GET    /api/nodes
GET    /api/nodes/{schema_id}
POST   /api/workflows/validate
POST   /api/workflows/compile
POST   /api/runs
GET    /api/runs/{run_id}
POST   /api/runs/{run_id}/pause
POST   /api/runs/{run_id}/resume
POST   /api/runs/{run_id}/cancel
POST   /api/runs/{run_id}/clear-cache
POST   /api/nodes/{node_id}/preview
GET    /api/artifacts/{artifact_id}
GET    /api/artifacts/{artifact_id}/thumbnail
GET    /api/settings
GET    /api/settings/schema
PUT    /api/settings
POST   /api/settings/reset/{section}
GET    /api/models
POST   /api/models/{model_id}/install
POST   /api/models/{model_id}/enable
POST   /api/models/{model_id}/disable
DELETE /api/models/{model_id}
GET    /api/downloads
POST   /api/downloads/{download_id}/cancel
POST   /api/system/release-models
GET    /api/diagnostics
WS     /api/events
```

All `/api` routes and the WebSocket handshake must require the session token.

## 6.3 Events

Define a versioned event envelope:

```json
{
  "version": 1,
  "eventId": "uuid",
  "timestamp": "ISO-8601",
  "type": "node.progress",
  "runId": "uuid",
  "nodeId": "node-uuid",
  "payload": {}
}
```

Support at least:

```text
backend.ready
backend.error
workflow.validated
run.queued
run.started
run.pause_requested
run.paused
run.resumed
run.cancel_requested
run.cancelled
run.completed
run.failed
node.queued
node.started
node.progress
node.preview
node.log
node.cached
node.completed
node.failed
node.skipped
artifact.created
download.queued
download.progress
download.completed
download.failed
download.cancelled
model.changed
settings.changed
worker.started
worker.restarted
worker.released
worker.crashed
```

Throttle high-frequency progress events without losing final state.

---

# 7. Remove Qt from Configuration

The current `backend/config.py` is coupled to qfluentwidgets and must be replaced.

Create a plain Python settings system using Pydantic models or dataclasses plus explicit validation.

Requirements:

- Preserve the current functional settings and defaults.
- Read the existing `config.json` format.
- Migrate it to a versioned new format without losing values.
- Back up corrupt or migrated files.
- Write settings atomically.
- Separate backend functional settings from frontend layout preferences.
- Emit a `settings.changed` event.
- Support section resets.
- Never import Qt or qfluentwidgets.

Preserve or map all current functional settings, including:

## Main and subtitle settings

- `subtitleSelectionAreas`
- `inpaintMode`
- `subtitleDetectMode`
- `subtitleYXAxisDifferencePixel`
- `subtitleAreaDeviationPixel`
- `subtitleAreaYAxisDifferencePixel`
- `subtitleAreaPixelToleranceYPixel`
- `subtitleAreaPixelToleranceXPixel`
- `subtitleTimelineBackwardFrameCount`
- `subtitleTimelineForwardFrameCount`
- `hardwareAcceleration`
- `checkUpdateOnStartup`
- `saveDirectory`

## STTN

- `sttnNeighborStride`
- `sttnReferenceLength`
- `sttnMaxLoadNum`
- Preserve the invariant that maximum load is not less than neighbor stride or reference length.

## ProPainter

- `propainterMaxLoadNum`

## Background removal

- `bgRemoveMode`
- `bgRemoveEnabledModels`

## Upscaling/enhancement

- `enhanceMode`
- `enhanceEnabledModels`
- `enhanceMaxLongEdge`
- `enhanceDenoiseEnabled`
- `enhanceDenoiseStrength`

## Low light

- `lowLightMode`
- `lowLightEnabledModels`
- `lowLightMaxLongEdge`

## Generation

- `generateMode`
- `generateEnabledModels`
- `generateWidth`
- `generateHeight`
- `generateSteps`

## Object selection

- `selectObjectMoreComplex`

## Inference worker

- `jobWatchdogSec`
- `inferIdleReleaseSec`
- `softDefaultsApplied`

Frontend-only preferences may be stored separately, including:

- Theme.
- Panel visibility.
- Panel sizes.
- Minimap visibility.
- Snap-to-grid.
- Grid size.
- Link animation.
- Auto-save interval.
- Confirm-before-delete preference.
- Canvas performance mode.
- Last workspace layout.

---

# 8. Main Application Layout

Create a professional dark desktop editor optimized for 1280x750 and larger displays.

The layout must be original Midgard work, while providing a workflow experience comparable in capability to chaiNNer.

## 8.1 Window regions

```text
┌──────────────────────────────────────────────────────────────┐
│ Native title/menu bar or custom secure title bar            │
├──────────────────────────────────────────────────────────────┤
│ Main toolbar: workflow actions and execution controls        │
├──────────────┬───────────────────────────────┬───────────────┤
│ Node library │ Infinite node canvas          │ Inspector /   │
│ and search   │                               │ preview       │
│              │                               │               │
├──────────────┴───────────────────────────────┴───────────────┤
│ Optional logs/downloads drawer                               │
├──────────────────────────────────────────────────────────────┤
│ Status bar: backend, worker, device, zoom, progress          │
└──────────────────────────────────────────────────────────────┘
```

Panels must be resizable and hideable. Persist layout preferences.

## 8.2 Toolbar

Provide:

- New workflow.
- Open workflow.
- Save.
- Undo.
- Redo.
- Add/search node.
- Validate workflow.
- Run workflow.
- Pause/resume.
- Stop.
- Clear workflow cache.
- Fit view.
- Toggle minimap.
- Toggle inspector.
- Toggle logs/downloads.

Execution controls must change state correctly and prevent invalid actions.

## 8.3 Left node library

Provide:

- Search with fuzzy matching.
- Recently used nodes.
- Favorites.
- Category tree.
- Model/capability availability badges.
- Missing-model warning.
- Drag to canvas.
- Click or Enter to add at viewport center.
- Keyboard navigation.
- Category collapse state persistence.

## 8.4 Right inspector

When a node is selected, show:

- Node name and icon.
- Description.
- Editable node label.
- Parameters.
- Input status.
- Output artifacts.
- Preview.
- Model selection.
- Device/capability information.
- Estimated resource use where available.
- Cache state.
- Last execution time.
- Warnings and validation errors.
- Run this node.
- Run from this node.
- Disable/bypass.
- Duplicate.
- Delete.

When no node is selected, show workflow properties and project metadata.

## 8.5 Bottom drawer

Provide tabs for:

- Run log.
- Node log.
- Model downloads.
- Diagnostics.
- Problems/validation.

The download experience must preserve the existing queue behavior, including active, pending, completed, failed and cancelled states.

---

# 9. Native and Context Menus

## 9.1 File menu

- New Workflow
- Open Workflow
- Open Recent
- Close Workflow
- Save
- Save As
- Import Workflow
- Export Workflow
- Export Canvas Image
- Reveal Project Folder
- Exit

## 9.2 Edit menu

- Undo
- Redo
- Cut
- Copy
- Paste
- Duplicate
- Delete
- Select All
- Deselect All
- Find Node
- Preferences

## 9.3 View menu

- Zoom In
- Zoom Out
- Actual Size
- Fit Workflow
- Center Selection
- Toggle Node Library
- Toggle Inspector
- Toggle Minimap
- Toggle Logs
- Toggle Downloads
- Reset Layout
- Full Screen
- Developer Tools only in development mode

## 9.4 Workflow menu

- Validate
- Run
- Run Selected
- Run From Selected
- Pause
- Resume
- Stop
- Clear Cache
- Clear Selected Cache
- Release GPU Models

## 9.5 Nodes menu

- Add Node
- Search Nodes
- Group Selection
- Ungroup
- Enable
- Disable
- Bypass
- Collapse
- Expand
- Align
- Distribute
- Auto Layout

## 9.6 Models menu

- Manage Models
- Download Queue
- Refresh Model Status
- Open Models Directory
- Release Loaded Models

## 9.7 Help menu

- Documentation
- Node Authoring Guide
- Keyboard Shortcuts
- Diagnostics
- Open Logs Folder
- Check for Updates
- Report an Issue
- Project Homepage
- About Midgard

## 9.8 Canvas context menu

- Add Node with search focus.
- Paste.
- Select All.
- Fit Workflow.
- Auto Layout.
- Create Group/Comment.

## 9.9 Node context menu

- Run Node.
- Run From Here.
- Preview.
- Enable/Disable.
- Bypass.
- Duplicate.
- Cut/Copy.
- Clear Cache.
- Collapse/Expand.
- Rename.
- Delete.
- Open documentation.

## 9.10 Edge context menu

- Delete connection.
- Insert node.
- Reroute.
- Inspect value/artifact.

---

# 10. Keyboard Shortcuts

Implement cross-platform shortcuts and display them in menus/tooltips.

Suggested defaults:

```text
Ctrl/Cmd+N             New workflow
Ctrl/Cmd+O             Open
Ctrl/Cmd+S             Save
Ctrl/Cmd+Shift+S       Save As
Ctrl/Cmd+Z             Undo
Ctrl/Cmd+Shift+Z       Redo
Ctrl/Cmd+C             Copy
Ctrl/Cmd+X             Cut
Ctrl/Cmd+V             Paste
Ctrl/Cmd+D             Duplicate
Delete/Backspace       Delete selection
Ctrl/Cmd+A             Select all
Space+drag             Pan canvas
Mouse wheel            Zoom according to preference
F                       Fit workflow
Shift+F                 Fit selection
Tab                     Open node search
Ctrl/Cmd+Enter         Run workflow
Space                   Pause/resume while running when focus permits
Escape                  Close menu/dialog or request stop confirmation
Ctrl/Cmd+,             Preferences
F11                     Full screen
```

Avoid stealing shortcuts while the user edits a text field.

---

# 11. Custom Tailwind Component System

Create Midgard-owned components under `frontend/src/components`.

At minimum:

```text
Button.jsx
IconButton.jsx
ToolbarButton.jsx
TextField.jsx
NumberField.jsx
TextArea.jsx
Select.jsx
Checkbox.jsx
Switch.jsx
Slider.jsx
Tabs.jsx
Dialog.jsx
ConfirmDialog.jsx
ContextMenu.jsx
DropdownMenu.jsx
Tooltip.jsx
Popover.jsx
Toast.jsx
ProgressBar.jsx
CircularProgress.jsx
Badge.jsx
Panel.jsx
SplitPane.jsx
Accordion.jsx
TreeView.jsx
SearchInput.jsx
VirtualList.jsx
EmptyState.jsx
ErrorBoundary.jsx
LoadingState.jsx
```

All components must support:

- Keyboard navigation.
- Visible focus rings.
- Appropriate ARIA attributes.
- Disabled states.
- Loading states.
- Error states.
- Escape-to-close where applicable.
- Click-outside behavior where applicable.
- Focus trapping and focus restoration for modal dialogs.
- Screen-reader labels for icon-only controls.
- Consistent density and spacing.
- No hidden dependency on a UI component framework.

Create semantic design tokens through CSS variables and Tailwind configuration:

```text
--mg-bg-app
--mg-bg-panel
--mg-bg-node
--mg-bg-node-selected
--mg-border
--mg-border-focus
--mg-text-primary
--mg-text-secondary
--mg-accent
--mg-success
--mg-warning
--mg-error
--mg-running
--mg-cached
```

Do not scatter raw arbitrary colors throughout components.

---

# 12. Node Graph Domain Model

## 12.1 Node schema

Define a versioned backend-owned node schema. The frontend renders nodes from this schema rather than hardcoding each backend operation.

Each node definition should contain fields similar to:

```json
{
  "schemaVersion": 1,
  "schemaId": "midgard.image.upscale",
  "version": 1,
  "name": "Upscale Image",
  "category": "Image/Enhance",
  "description": "Upscales an image using an installed enhancement model.",
  "icon": "zoom-in",
  "kind": "processor",
  "inputs": [],
  "outputs": [],
  "parameters": [],
  "capabilities": [],
  "cachePolicy": "content-addressed",
  "sideEffects": false,
  "supportsPreview": true,
  "supportsCancel": true,
  "supportsPause": false
}
```

## 12.2 Port types

Implement strict typed ports:

```text
IMAGE
MASK
ALPHA
VIDEO
AUDIO
FRAMES
TEXT
PROMPT
PATH
DIRECTORY
NUMBER
INTEGER
BOOLEAN
ENUM
COLOR
SEED
MODEL
METADATA
ARTIFACT
```

Each type must have:

- Stable internal ID.
- Human label.
- Port color token.
- Compatibility rules.
- Serialization rules.
- Runtime validation.

Do not rely solely on port color for meaning. Include labels and accessible descriptions.

Allow explicitly declared safe coercions only, for example `INTEGER -> NUMBER`. Do not silently coerce `IMAGE -> MASK`, `TEXT -> PATH`, or incompatible model types.

## 12.3 Node instance

A workflow node instance must contain:

```json
{
  "id": "uuid",
  "schemaId": "midgard.image.upscale",
  "schemaVersion": 1,
  "label": "Upscale portrait",
  "position": {"x": 100, "y": 200},
  "parameters": {},
  "disabled": false,
  "bypass": false,
  "collapsed": false
}
```

## 12.4 Edge instance

An edge must contain:

```json
{
  "id": "uuid",
  "sourceNodeId": "uuid",
  "sourcePortId": "image",
  "targetNodeId": "uuid",
  "targetPortId": "image"
}
```

## 12.5 Validation

Validate:

- Required inputs.
- Port compatibility.
- Missing models.
- Missing files.
- Invalid parameter ranges.
- Duplicate single-input connections.
- Unsupported cycles.
- Unreachable output nodes.
- Side-effect nodes with missing destinations.
- Unsupported hardware.
- Invalid workflow schema versions.
- Node migrations.

Do not allow cycles in the first production implementation unless an explicit future feedback/loop node is designed.

---

# 13. Node Canvas Behavior

Implement:

- Infinite pan and zoom canvas.
- Dot or line grid background.
- Optional snap-to-grid.
- Minimap.
- Fit view.
- Box selection.
- Multi-selection.
- Shift-add selection.
- Node dragging.
- Group dragging.
- Edge creation.
- Edge reconnection.
- Edge deletion.
- Node deletion.
- Copy/cut/paste.
- Duplicate with offset.
- Undo/redo for graph edits.
- Drag files onto the canvas to create appropriate load nodes.
- Search-to-add node menu.
- Add compatible node when a loose connection is dropped on empty canvas.
- Filter node search to compatible input/output types when opened from a loose connection.
- Insert a compatible node into an existing edge with an explicit modifier gesture.
- Auto-layout using ELK.js or another permissively licensed layout engine.
- Comments/groups/frames.
- Collapsible nodes.
- Custom node labels.
- Validation badges.
- Missing-model badges.
- Preview thumbnails where useful.

## 13.1 Node visual states

Support:

```text
IDLE
INVALID
QUEUED
RUNNING
PAUSE_REQUESTED
PAUSED
CACHED
SUCCEEDED
FAILED
CANCELLED
SKIPPED
DISABLED
```

Show node progress and status without causing canvas layout jumps.

## 13.2 Edge visual states

Support:

- Normal typed edge.
- Selected edge.
- Invalid attempted connection.
- Running/active edge animation.
- Completed path.
- Failed path.
- Disabled/bypassed path.

Animate only active execution paths and respect reduced-motion preferences.

## 13.3 Performance

The canvas must remain responsive with at least:

- 250 nodes.
- 500 edges.
- Live progress updates.
- Minimap enabled.

Avoid rerendering every node on every progress event. Use selector-based state subscriptions and batched event updates.

---

# 14. Workflow and Project Format

Use a versioned Midgard workflow/project format, for example:

```text
*.midgard.json
```

The project document must include:

```json
{
  "format": "midgard-workflow",
  "version": 1,
  "projectId": "uuid",
  "name": "Workflow name",
  "createdAt": "ISO-8601",
  "updatedAt": "ISO-8601",
  "nodes": [],
  "edges": [],
  "groups": [],
  "projectSettings": {},
  "viewport": {},
  "metadata": {}
}
```

Requirements:

- Atomic saves.
- Dirty-state tracking.
- Auto-save recovery.
- Crash recovery.
- Recent files.
- Save As.
- Format migrations.
- Unknown-field preservation where safe.
- Missing-file relinking.
- Relative paths when media is inside the project directory.
- Explicit external-file references otherwise.
- Original media must remain byte-for-byte unchanged.
- Generated artifacts must have lineage back to inputs, node, parameters, model revision and workflow revision.

Never write generated outputs over source files unless the user explicitly chooses and confirms an overwrite operation.

---

# 15. Artifact Store and Caching

Create a local artifact abstraction.

Each artifact should record:

- Artifact ID.
- Media type.
- Absolute internal path.
- Original source path when applicable.
- Content hash.
- Byte size.
- Width and height for images.
- Frame count, timebase, duration and streams for video.
- Alpha/color metadata where available.
- Creating run and node.
- Input artifact IDs.
- Model/code revision.
- Parameters hash.
- Created timestamp.

Use artifact references between graph execution stages.

Implement node caching based on:

```text
node schema ID and version
+ normalized parameters
+ input artifact hashes
+ relevant settings
+ model identifier and revision
+ processing implementation revision
```

Expose clear-cache actions for the workflow and selected nodes.

Cache writes must be atomic. Incomplete or cancelled outputs must not become valid cache entries.

---

# 16. Graph Compilation and Execution

Implement this pipeline:

```text
Workflow document
→ schema validation
→ semantic validation
→ dependency graph
→ topological ordering
→ capability/model checks
→ cache analysis
→ execution plan
→ sequential/shared-worker jobs
→ artifacts and events
→ final workflow result
```

## 16.1 Shared GPU scheduling

Preserve the current one-GPU-job-at-a-time safety rule.

Initial scheduler rules:

- Execute GPU-heavy nodes sequentially.
- Never load two incompatible heavy model families concurrently.
- Reuse a warm model only when safe.
- Release models on explicit reset or resource pressure.
- Use the existing InferClient as the worker boundary unless a carefully tested replacement is necessary.
- Do not bypass the existing watchdog and crash-recovery behavior.

CPU-only metadata and lightweight utility operations may run concurrently only after correctness and bounded-resource behavior are proven.

## 16.2 Run modes

Support:

- Run entire workflow.
- Run selected node.
- Run selected subgraph.
- Run from selected node to outputs.
- Preview selected node.
- Re-run failed nodes.
- Skip cached nodes.
- Force re-run.

## 16.3 Pause behavior

Do not falsely claim that every model can pause mid-kernel.

Implement two pause levels:

1. Graph-level pause at safe node boundaries.
2. Adapter-level pause only for operations that truly support it.

When pause is requested during a non-pausable node:

- Emit `run.pause_requested`.
- Let the current operation reach a safe boundary.
- Do not start the next node.
- Transition to `run.paused`.

Resume continues from the existing plan and valid completed artifacts.

## 16.4 Cancellation

Cancellation must:

- Stop queued nodes.
- Request soft cancellation where supported.
- Use hard worker cancellation for existing hard-cancel job types.
- Clean temporary files.
- Preserve previously committed valid artifacts.
- Mark incomplete outputs invalid.
- Return the worker to a known healthy state.
- Emit clear cancellation events.

## 16.5 Failure handling

Classify errors:

```text
VALIDATION
MISSING_INPUT
MISSING_MODEL
MODEL_LICENSE_BLOCK
UNSUPPORTED_HARDWARE
OUT_OF_MEMORY
CANCELLED
TIMEOUT
WORKER_CRASH
MEDIA_DECODE
MEDIA_ENCODE
FILESYSTEM
PERMISSION
INTERNAL
```

Each failure must provide:

- Human-readable message.
- Stable error code.
- Node ID.
- Retryability.
- Suggested actions.
- Structured diagnostic details.
- Log reference.

---

# 17. Initial Node Catalog

Register nodes by capability, not by arbitrary page names.

## 17.1 Input nodes

- Load Image
- Load Images
- Load Video
- Load Mask
- Load Text
- Prompt
- Number
- Integer
- Boolean
- Seed
- Color
- Select File
- Select Directory

## 17.2 Generation nodes

- Generate Image
- Image-to-Image when supported by existing models
- Inpaint from Image + Mask
- Outpaint when supported

## 17.3 Selection and mask nodes

- Select Object by Click
- Select Object by Text
- Detect Text Regions
- Detect Subtitle Regions
- Create Mask from Detection
- Expand Mask
- Contract Mask
- Blur/Feather Mask
- Invert Mask
- Combine Masks
- Mask Editor

## 17.4 Removal and retouch nodes

- Remove Background
- Remove Text from Image
- Remove Text from Video
- LaMa Retouch
- Inpaint Image
- Composite Image with Mask

## 17.5 Enhancement nodes

- Upscale Image
- Denoise Image
- Fix Low Light
- Resize Image
- Crop Image
- Pad Image
- Sharpen when an existing implementation exists
- Face Restore only when an approved implementation and model license exist

## 17.6 Output and utility nodes

- Preview Image
- Compare Images
- Preview Video
- Save Image
- Save Video
- Copy Artifact
- Show Metadata
- Workflow Note/Comment

Do not expose a node unless it has a valid backend implementation, a clearly marked disabled state, or an explicit development-only feature flag.

---

# 18. Existing Job-Type Adapters

Create node adapters for the current `JobType` values:

```text
enhance
low_light
generate
bg_remove
lama_retouch
select_subject
subtitle
```

Each adapter must:

- Validate inputs and parameters.
- Convert artifact references to the existing path-based payload.
- Invoke `InferClient.start_job`.
- Map callbacks to structured graph events.
- Commit output artifacts only after success.
- Map `BUSY`, cancellation, timeout and crash outcomes to stable error codes.
- Declare cancellation behavior.
- Declare expected resource class.
- Declare required models and hardware.
- Include tests using a fake inference client.

Do not let React or the API routes construct raw worker payloads directly. Payload construction belongs in backend adapters.

---

# 19. Preview and Retouch Experience

## 19.1 Image preview

Provide:

- Fit, fill and 100% zoom.
- Zoom range equivalent to the current useful behavior.
- Pan.
- Checkerboard transparency.
- Pixel dimensions.
- Before/after comparison.
- Split view.
- Background color selection.
- Save/reveal output.

Use optimized thumbnails/proxies for interactive display while preserving full-resolution artifacts for processing and export.

## 19.2 Mask editor

Rebuild the current mask/retouch behavior as a React canvas tool.

Support:

- Brush add/remove.
- Eraser.
- Lasso/polygon selection.
- Rectangle selection.
- Object selection through existing backend models.
- Mask overlay opacity.
- Edge feather/expand controls.
- Undo/redo.
- Clear/invert mask.
- Full-resolution mask output.
- Preview-resolution interaction mapped accurately to source pixels.

Do not perform destructive edits on the original media.

Use Canvas 2D, WebGL, or another browser-native rendering method after measuring performance. Keep the authoritative mask as an artifact, not as an opaque browser-only state.

## 19.3 Video preview

Support:

- Playback.
- Scrubbing.
- Current time/frame display.
- Subtitle/text detection overlays.
- Selection-area editing.
- Proxy preview.
- Preservation of source timing information in backend processing.

Do not assume constant frame rate. Preserve source timebase, timestamps, audio and rotation metadata unless an explicit node changes them.

---

# 20. Settings Screen

Preserve the existing settings content and group order while rebuilding the interface in React and Tailwind.

Use collapsible card-like sections with reset actions.

Required groups:

1. Subtitle Detection
2. STTN
3. ProPainter
4. Background Removal Models
5. Upscale/Enhance Models
6. Low-Light Models
7. Generation Models
8. Object Selection Models
9. Node Editor
10. Advanced
11. About

## 20.1 Model groups

Each model card must show:

- Model name.
- Capability.
- Installed/not installed.
- Enabled/disabled.
- Download size.
- Disk usage.
- License identifier and usage warning.
- Required hardware.
- Download progress.
- Install.
- Enable.
- Disable.
- Remove.
- Open model location where safe.
- Error/retry state.

Preserve one global download queue and bottom-right compact download notifications, with the full queue visible in the bottom drawer.

## 20.2 Node Editor settings

Include:

- Snap to grid.
- Grid size.
- Show minimap.
- Animate active links.
- Show node previews.
- Confirm node deletion.
- Auto-save interval.
- Canvas performance mode.
- Edge style.
- Reduced motion.
- Reset editor layout.

## 20.3 Advanced settings

Preserve:

- Save directory.
- Hardware acceleration master switch where still appropriate.
- Check for updates on startup.
- Worker watchdog settings behind an advanced/developer disclosure.
- Release loaded models.
- Open data, models, cache and logs directories.
- Clear caches with confirmation.

## 20.4 About

Show:

- Midgard version.
- Python backend version.
- Frontend build revision.
- License.
- Project homepage.
- Releases.
- Issue reporting.
- Third-party notices.
- System and acceleration summary.

---

# 21. State Management

Separate state into:

## 21.1 Editor state

- Nodes.
- Edges.
- Selection.
- Viewport.
- Undo/redo history.
- Clipboard.
- Groups.
- Dirty state.

## 21.2 Run state

- Current run.
- Per-node state.
- Per-node progress.
- Overall progress.
- Logs.
- Artifacts.
- Pause/cancel state.

## 21.3 Server state

- Node definitions.
- Models.
- Settings.
- Capabilities.
- Downloads.
- Diagnostics.

## 21.4 Desktop state

- Window layout.
- Recent files.
- Native menu state.
- File grants.

Avoid a single giant global store. Use narrow selectors to prevent unnecessary node rerenders.

---

# 22. Undo and Redo

Undo/redo must cover user graph edits:

- Add/delete/move node.
- Add/delete/reconnect edge.
- Parameter change.
- Rename node.
- Group changes.
- Collapse/bypass/disable changes.
- Paste and duplicate.
- Auto-layout as one transaction.

Do not place execution progress, downloads, logs, or backend status in the undo history.

Coalesce continuous slider changes and node dragging into sensible history entries.

---

# 23. Model and License Safety

Midgard is currently Apache-2.0 licensed. Preserve that license unless the repository owner explicitly changes it.

Rules:

- Do not copy GPL-licensed chaiNNer or ComfyUI source code into Midgard.
- Do not copy their branding or visual assets.
- Use them only as behavioral references.
- Record the exact license of every new JavaScript and Python dependency.
- Record code licenses separately from model-weight licenses.
- Preserve existing model restrictions and warnings.
- Do not enable research-only or non-commercial models by default in a commercial/release profile.
- Generate or update third-party notices.
- Pin dependencies used in releases.
- Record model revisions/checksums where supported.

Fail the release audit for unknown or incompatible licenses.

---

# 24. Packaging and Installation

Preserve Midgard's supported release profiles:

```text
Windows x64: CPU, CUDA, DirectML
Linux x86-64: CPU, CUDA
macOS Intel/Apple Silicon as supported: MPS/CPU
```

The final installer/package must contain:

- Electron application.
- Production renderer bundle.
- Embedded Python 3.12 runtime or the repository's approved packaged runtime strategy.
- Backend code.
- Required Python dependencies for the selected profile.
- Required static resources.
- License and notices.

Requirements:

- No global Python requirement for packaged users.
- No global Node.js requirement for packaged users.
- Backend launches without a terminal window on Windows.
- Clean shutdown.
- Correct application data paths.
- Upgrade preserves settings, installed models and workflows.
- Uninstall behavior is documented.
- Large models remain outside immutable application resources.
- Development and packaged path resolution are tested separately.
- Code signing/notarization hooks remain compatible with the existing release workflow.

Update installers, launchers, README and CI. Replace `run_gui.*` naming with appropriate Midgard/Electron launch commands while preserving useful compatibility redirects only when harmless.

---

# 25. Migration Plan

Implement in controlled phases on a dedicated branch. The final merged state must contain only the Electron GUI.

## Phase 0: Repository audit and safeguards

- Check current branch and working tree.
- Do not overwrite unrelated user changes.
- Inventory all PySide6, Qt and qfluentwidgets imports.
- Inventory current settings access patterns.
- Inventory current model-manager services.
- Inventory installer/release assumptions.
- Record architecture decisions in an ADR.
- Add characterization tests around current backend behavior before changing it.

Exit gate:

- Backend behavior and Qt coupling are documented.
- Existing focused test suite passes or failures are documented.

## Phase 1: Qt-free settings and backend startup

- Replace qfluentwidgets configuration with plain Python models.
- Add config migration and tests.
- Refactor backend modules that assume `.value` properties or Qt signals.
- Introduce backend service startup.
- Preserve current AI execution behavior.

Exit gate:

- Backend imports and starts in a Python environment without PySide6/qfluentwidgets installed.
- Settings migration tests pass.

## Phase 2: API and graph contracts

- Add versioned node, workflow, settings and event contracts.
- Add node registry.
- Add validation/compiler skeleton.
- Add authenticated FastAPI/WebSocket service.
- Adapt InferClient events.

Exit gate:

- API contract tests pass.
- Fake-worker workflow can run from API to artifact result.

## Phase 3: Electron shell and custom UI foundation

- Add Electron Forge/Vite.
- Add React JavaScript renderer.
- Add Tailwind.
- Add secure preload bridge.
- Add Python process supervision.
- Add custom components.
- Add base window layout and native menus.

Exit gate:

- Electron launches, starts Python, reaches ready state and exits cleanly.
- Security smoke tests pass.

## Phase 4: First vertical slice

Implement fully:

```text
Load Image → Upscale Image → Preview Image → Save Image
```

This slice must include:

- Node definitions.
- Typed links.
- Workflow save/load.
- Validation.
- Graph compilation.
- Existing enhancement worker adapter.
- Progress.
- Preview.
- Cancellation.
- Output artifact.
- Cache.
- Tests.

Exit gate:

- The slice works in development and packaged smoke builds.
- No manual Python script is required.

## Phase 5: Existing image capabilities

Add:

- Generate Image.
- Remove Background.
- Fix Low Light.
- Select Object.
- LaMa Retouch.
- Mask utilities.
- Image save/compare.

Exit gate:

- Existing image capabilities are available through nodes with equivalent functional settings.

## Phase 6: Subtitle and video capabilities

Add:

- Load Video.
- Text/subtitle detection.
- Selection-area editor.
- Remove Text from Video.
- Video preview.
- Save Video.

Exit gate:

- Source timing/audio/rotation requirements are verified by integration fixtures.

## Phase 7: Settings and model management

- Rebuild all settings groups.
- Rebuild model cards and download queue.
- Add update UI and diagnostics.

Exit gate:

- Existing settings and model actions are available without Qt.

## Phase 8: Packaging and release migration

- Update installers.
- Update CI.
- Add profile-specific Electron packaging.
- Test clean install, upgrade, rollback and uninstall.

Exit gate:

- At least one supported packaged profile passes end-to-end smoke tests.

## Phase 9: Remove the old GUI completely

Delete from the final repository and production application:

```text
gui.py
ui/
PySide6 dependencies
qfluentwidgets dependencies
Qt-specific tests
Qt bootstrap validation
Qt launcher code
Qt packaging resources that are no longer needed
```

Update tests and documentation.

Add a CI guard that fails when production code or dependencies contain:

```text
PySide6
PyQt
qfluentwidgets
QtCore
QtGui
QtWidgets
```

Allow these strings only in explicit migration history/documentation fixtures when necessary.

Exit gate:

- No importable production code depends on Qt.
- `pip install` for backend requirements does not install Qt.
- Electron is the only GUI.

---

# 26. Testing Requirements

## 26.1 Python tests

Use pytest for:

- Settings migration.
- Atomic settings writes.
- Node-schema validation.
- Workflow validation.
- Cycle detection.
- Type compatibility.
- Graph compilation.
- Topological ordering.
- Cache keys.
- Artifact commit/cleanup.
- InferClient adapters.
- Cancellation.
- Worker crash recovery.
- API authentication.
- API contracts.
- WebSocket event ordering.
- Path and permission safety.
- Model-manager actions with fakes.
- No-network operation.

## 26.2 Frontend unit/component tests

Use Vitest and React Testing Library for:

- Custom components.
- Keyboard navigation.
- Dialog focus trap.
- Menus.
- Node library search.
- Port compatibility UI.
- Node inspector.
- Settings forms.
- Download queue.
- Run controls.
- Undo/redo.
- Workflow serialization.
- Event-store updates.

## 26.3 End-to-end tests

Use Playwright Electron support for:

- Launch and backend readiness.
- New/open/save workflow.
- Add and connect nodes.
- Reject invalid connections.
- Run the fake-worker vertical slice.
- Progress display.
- Pause request.
- Stop/cancel.
- Settings persistence.
- Model download fake flow.
- Window close and backend shutdown.
- Recovery from backend startup failure.

## 26.4 Golden media tests

Use small synthetic or permissively licensed fixtures for:

- Image metadata preservation.
- Alpha handling.
- Mask alignment.
- Upscale dimensions.
- Video timestamps and audio stream preservation.
- Cancellation cleanup.

Do not require multi-gigabyte model downloads in the default CI suite.

## 26.5 Static guards

Add checks for:

- No Qt imports.
- No forbidden UI frameworks.
- No TypeScript application files.
- No renderer Node integration.
- No unrestricted preload APIs.
- Contract/schema validity.
- Dependency licenses.

---

# 27. Performance and Resource Requirements

- Renderer idle CPU use should remain low.
- Progress events must be throttled and batched.
- Do not decode full videos into memory by default.
- Do not load full-resolution images repeatedly for thumbnails.
- Use bounded thumbnail caches.
- Free object URLs and canvas resources.
- Ensure closed previews release memory.
- Keep ML imports out of API startup where possible.
- Lazy-load models through existing worker paths.
- Avoid duplicate model processes.
- Preserve one-heavy-GPU-job behavior.
- Record peak memory/VRAM where practical.
- Add a bounded OOM fallback policy for operations that support tiling or lower-resource modes.

---

# 28. Accessibility and UX Quality

The application must be usable without a mouse for menus, settings and common workflow actions.

Requirements:

- Visible keyboard focus.
- ARIA labels.
- Semantic buttons and form fields.
- Tooltips are supplemental, not the only labels.
- Color is not the only status indicator.
- Reduced-motion support.
- High-contrast focus and error states.
- Scalable UI text.
- No tiny click targets.
- Destructive actions require appropriate confirmation.
- Errors identify the affected node and offer an action.
- Empty states teach the next action.
- Long-running operations never freeze the renderer.

---

# 29. Documentation Deliverables

Create or update:

```text
README.md
docs/ELECTRON_ARCHITECTURE.md
docs/NODE_AUTHORING.md
docs/WORKFLOW_FORMAT.md
docs/API.md
docs/SETTINGS_MIGRATION.md
docs/RELEASE_PACKAGING.md
docs/KEYBOARD_SHORTCUTS.md
docs/adr/ADR-electron-node-editor.md
THIRD_PARTY_NOTICES.md
```

README must explain:

- Electron is now the GUI.
- Python remains the processing backend.
- How to install frontend and backend development dependencies.
- How to run development mode.
- How to run tests.
- How to build packages.
- Where models, settings, workflows, cache and logs are stored.

---

# 30. Developer Commands

Provide consistent root commands, for example:

```text
npm install
npm run dev
npm run dev:frontend
npm run dev:backend
npm run lint
npm run check
npm run test
npm run test:frontend
npm run test:backend
npm run test:e2e
npm run package
npm run make
```

Use a root task runner or npm workspaces only when it reduces complexity. Do not force Python package installation through npm; call explicit Python scripts or documented virtual-environment commands.

Provide Windows, Linux and macOS development instructions.

---

# 31. Codex Working Rules

Follow these rules while implementing:

1. Inspect before editing.
2. Preserve unrelated user changes.
3. Do not rewrite working AI code without evidence.
4. Change contracts before cross-process implementations.
5. Keep commits and changes logically grouped.
6. Add tests with each behavior change.
7. Run focused tests frequently and the full appropriate suite before completion.
8. Do not claim a feature works without executing its tests or a documented manual smoke check.
9. Do not leave silent exception swallowing in new code.
10. Use structured logging.
11. Use atomic writes for settings, workflows and final artifacts.
12. Never pass huge media arrays through IPC/JSON.
13. Never expose arbitrary filesystem or shell access to the renderer.
14. Never import ML runtimes in the renderer.
15. Never import Qt in the final backend.
16. Do not use placeholder UI libraries contrary to this prompt.
17. Do not copy chaiNNer source code.
18. Do not remove legacy behavior until its replacement is tested.
19. The final merged product must not ship both GUIs.
20. Be honest in the final report about incomplete items and limitations.

When a repository fact conflicts with this prompt, prefer the repository's current functional behavior unless it violates a non-negotiable final-state requirement. Document the conflict and the chosen migration.

---

# 32. Required Implementation Report

At the end of each phase, report:

```text
Phase completed
User-visible outcome
Contracts changed
Files added
Files modified
Files deleted
Settings/storage migrations
Tests added
Commands run
Test results
Packaging impact
Security impact
License/dependency impact
Known limitations
Next phase
```

The final report must include a file-by-file summary and explicit proof that PySide6/qfluentwidgets were removed.

---

# 33. Final Acceptance Criteria

The migration is complete only when all of the following are true:

## Desktop shell

- Midgard launches as an Electron desktop application.
- Python starts automatically and invisibly.
- Backend readiness is checked before the editor opens.
- Closing Midgard shuts down backend and worker processes.
- Secure Electron settings and preload allowlists are verified.

## GUI stack

- React uses JavaScript/JSX.
- `@xyflow/react` renders the workflow canvas.
- Tailwind CSS is the only UI styling framework.
- Midgard custom components implement menus, dialogs, controls and panels.
- No Chakra, MUI, Mantine, shadcn, Radix, Bootstrap, Fluent UI or equivalent UI framework exists in dependencies.

## Qt removal

- PySide6 is absent from production requirements.
- qfluentwidgets is absent from production requirements.
- No production Python file imports Qt.
- `gui.py` and the old `ui/` package are deleted from the final repository and are not shipped.
- Qt GUI tests and bootstrap checks are removed or replaced.
- CI contains a no-Qt guard.

## Node editor

- Nodes can be added, moved, selected, copied, pasted, deleted and grouped.
- Typed links can be created, reconnected and deleted.
- Invalid connections are blocked with an explanation.
- Search and category browsing work.
- Minimap, zoom, pan, fit and snap-to-grid work.
- Undo/redo works.
- Workflows save, load and recover.
- Context menus and keyboard shortcuts work.

## Execution

- Workflows validate and compile in Python.
- Existing AI operations are invoked through adapters.
- One GPU-heavy job runs at a time.
- Per-node and overall progress display correctly.
- Preview events work.
- Cancellation works.
- Pause-at-safe-boundary works.
- Worker crashes are surfaced and recovered safely.
- Outputs are committed as artifacts with lineage.
- Cache behavior is deterministic and clearable.

## Existing Midgard functionality

- Generate Image is available.
- Remove Text/Subtitle is available for supported media.
- Remove Background is available.
- Upscale is available.
- Fix Low Light is available.
- Object selection/masking is available.
- LaMa retouch/inpaint is available.
- Model install/enable/disable/remove works.
- Existing functional settings migrate and remain editable.

## Packaging

- Development startup is documented.
- At least one packaged profile passes a clean-machine smoke test.
- Packaged users do not need global Python or Node.js.
- Offline operation works after required models are installed.
- Settings and installed models survive upgrades.
- Licenses and third-party notices are included.

## Quality

- Python tests pass.
- Frontend tests pass.
- Contract tests pass.
- Electron end-to-end smoke tests pass.
- No-Qt and forbidden-framework guards pass.
- Security smoke tests pass.
- Known limitations are documented.

---

# 34. First Action

Begin by inspecting the repository and produce a concise implementation inventory before modifying files:

1. Current branch and working tree state.
2. Current application startup path.
3. All Qt/qfluentwidgets import locations.
4. All settings consumers.
5. Existing inference job entry points and payload shapes.
6. Existing model-manager and download services.
7. Existing installer and release workflow assumptions.
8. Existing test coverage.
9. Proposed files for Phase 1.
10. Risks that could break existing AI processing.

Then implement Phase 1. Do not stop after producing the inventory unless a hard repository or environment blocker makes safe implementation impossible.
