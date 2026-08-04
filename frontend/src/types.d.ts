export type PortType =
  | "IMAGE" | "MASK" | "ALPHA" | "VIDEO" | "AUDIO" | "FRAMES"
  | "TEXT" | "PROMPT" | "PATH" | "DIRECTORY" | "NUMBER" | "INTEGER"
  | "BOOLEAN" | "ENUM" | "COLOR" | "SEED" | "MODEL";

export interface PortDefinition {
  id: string;
  label: string;
  type: PortType;
  required?: boolean;
  multiple?: boolean;
  description?: string;
}

export interface ParameterOption {
  value: string | number;
  label: string;
  description?: string;
  disabled?: boolean;
  modelId?: string;
}

export interface ParameterDefinition {
  id: string;
  label: string;
  type: string;
  default?: unknown;
  required?: boolean;
  minimum?: number;
  maximum?: number;
  step?: number;
  options?: ParameterOption[];
  description?: string;
}

export interface ModelInventory extends Record<string, unknown> {
  id: string;
  display_name: string;
  purpose: string;
  framework: string;
  license: string;
  installed: boolean;
  enabled: boolean;
  state: string;
  disk_usage_bytes: number;
  can_install: boolean;
  can_uninstall: boolean;
  can_toggle: boolean;
}

export interface DownloadJob {
  jobId: number;
  kind: string;
  key: string;
  modelId?: string | null;
  operation: string;
  state: "active" | "stopping" | "queued" | "completed" | "failed" | "cancelled";
  position: number;
  progress?: number | null;
  detail?: string;
  error?: string;
  downloadedBytes?: number | null;
  totalBytes?: number | null;
  bytesPerSecond?: number | null;
  elapsedSeconds?: number;
  etaSeconds?: number | null;
}

export interface DownloadQueueState {
  active: DownloadJob[];
  pending: DownloadJob[];
  recent: DownloadJob[];
}

export interface NodeDefinition {
  schemaId: string;
  schemaVersion: number;
  version?: number;
  name: string;
  category?: string;
  description?: string;
  icon?: string;
  kind?: "input" | "processor" | "output";
  inputs: PortDefinition[];
  outputs: PortDefinition[];
  parameters: ParameterDefinition[];
  capabilities?: string[];
  requiredModels?: string[];
  supportsPreview?: boolean;
  available?: boolean;
  unavailableReason?: string;
}

export interface ArtifactResult {
  status?: string;
  artifactIds?: string[];
  completedAt?: string;
  sourceName?: string;
}

export interface ArtifactMetadata {
  mediaType?: string;
  width?: number;
  height?: number;
  byteSize?: number;
  duration?: number;
  frameCount?: number;
  alpha?: boolean;
}

export interface ArtifactPreviewState {
  url: string | null;
  metadata: ArtifactMetadata | null;
  error: string | null;
}

export interface WorkflowNodeData extends Record<string, unknown> {
  schemaId: string;
  schemaVersion: number;
  label: string;
  parameters: Record<string, unknown>;
  appearance: Record<string, unknown>;
  definition?: NodeDefinition;
  result?: ArtifactResult | null;
  disabled?: boolean;
  collapsed?: boolean;
  nodeActions?: {
    onOpen?: (id: string) => void;
    onRun?: (id: string) => void;
    onPreview?: (id: string) => void;
    onModelChange?: (id: string, value: string | number) => void;
    onParameterChange?: (id: string, key: string, value: unknown) => void;
  };
  modelInventory?: ModelInventory[];
}

export interface SerializedWorkflowNode {
  id: string;
  schemaId: string;
  schemaVersion: number;
  label?: string;
  position: {x: number; y: number};
  parameters?: Record<string, unknown>;
  appearance?: Record<string, unknown>;
  result?: ArtifactResult | null;
  disabled?: boolean;
  collapsed?: boolean;
}

export interface SerializedWorkflowEdge {
  id: string;
  sourceNodeId: string;
  sourcePortId: string;
  targetNodeId: string;
  targetPortId: string;
}

export interface WorkflowDocument {
  format: "midgard-workflow";
  version: number;
  projectId: string;
  name: string;
  createdAt?: string;
  updatedAt?: string;
  nodes: SerializedWorkflowNode[];
  edges: SerializedWorkflowEdge[];
  groups: WorkflowGroup[];
  projectSettings?: Record<string, unknown>;
  viewport?: { x: number; y: number; zoom: number };
  metadata?: Record<string, unknown>;
}

export interface DesktopGrant {
  grantId: string;
  artifactId?: string;
  name: string;
  mediaType?: string;
  width?: number;
  height?: number;
  byteSize?: number;
  alpha?: boolean;
}

export interface MidgardDesktopApi {
  getBackendSession(): Promise<{ baseUrl: string; token: string }>;
  newWorkflow(): Promise<WorkflowDocument>;
  openWorkflow(): Promise<{ document: WorkflowDocument; name: string; displayPath: string } | null>;
  saveWorkflow(document: unknown): Promise<{ saved: boolean; name: string; displayPath: string } | null>;
  saveWorkflowAs(document: unknown): Promise<{ saved: boolean; name: string; displayPath: string } | null>;
  autosaveWorkflow(document: unknown): Promise<boolean>;
  recoverWorkflow(): Promise<WorkflowDocument | null>;
  clearRecovery(): Promise<void>;
  selectImageFiles(): Promise<DesktopGrant[]>;
  registerDroppedFiles(files: File[]): Promise<DesktopGrant[]>;
  selectVideoFiles(): Promise<DesktopGrant[]>;
  selectMaskFile(): Promise<DesktopGrant | null>;
  selectDirectory(): Promise<DesktopGrant | null>;
  selectSaveFile(kind: "image" | "video"): Promise<DesktopGrant | null>;
  revealPath(grantId: string): Promise<boolean>;
  openExternal(urlId: string): Promise<void>;
  getPlatformInfo(): Promise<Record<string, unknown>>;
  setRunProgress(progress: number): void;
  onMenuCommand(callback: (command: string) => void): () => void;
}

export type EditorNode = import("@xyflow/react").Node<WorkflowNodeData>;
export type EditorEdge = import("@xyflow/react").Edge<Record<string, unknown>>;

export interface WorkflowGroup {
  id: string;
  kind: string;
  label: string;
  nodeIds: string[];
  startNodeIds: string[];
  position: { x: number; y: number };
  width: number;
  height: number;
  color: string;
  appearance: Record<string, unknown>;
}

export interface EditorProject {
  format: "midgard-workflow";
  version: number;
  projectId: string;
  name: string;
  createdAt?: string;
  updatedAt?: string;
  projectSettings?: Record<string, unknown>;
  viewport?: { x: number; y: number; zoom: number };
  metadata?: Record<string, unknown>;
}

export interface EditorSnapshot {
  nodes: EditorNode[];
  edges: EditorEdge[];
  groups: WorkflowGroup[];
}

export interface ConnectionResult { valid: boolean; reason: string }

export interface ValidationIssue {
  severity: "error" | "warning";
  code: string;
  message: string;
  nodeId?: string;
  edgeId?: string;
  action?: string;
}

export interface EditorState extends EditorSnapshot {
  selectedGroupId: string | null;
  past: EditorSnapshot[];
  future: EditorSnapshot[];
  dirty: boolean;
  project: EditorProject;
  definitions: NodeDefinition[];
  setDefinitions(definitions: NodeDefinition[]): void;
  addNode(schemaId: string, position?: {x: number; y: number}): string | null;
  onNodesChange(changes: import("@xyflow/react").NodeChange<EditorNode>[]): void;
  onEdgesChange(changes: import("@xyflow/react").EdgeChange<EditorEdge>[]): void;
  canConnect(connection: import("@xyflow/react").Connection | EditorEdge): ConnectionResult;
  connect(connection: import("@xyflow/react").Connection): ConnectionResult;
  removeEdge(id: string): void;
  updateNode(id: string, patch: Partial<WorkflowNodeData>): void;
  setNodeModel(id: string, value: string | number): void;
  recordNodeResult(id: string, result: Partial<ArtifactResult>): void;
  selectAll(): void;
  deselect(): void;
  focusNode(id: string): void;
  deleteSelected(): void;
  copySelected(): void;
  duplicateSelected(): void;
  paste(): void;
  groupSelected(): string | null;
  createFlowFromSelected(): string | null;
  selectGroup(id: string): void;
  updateGroup(id: string, patch: Partial<WorkflowGroup>): void;
  fitGroup(id: string): void;
  removeGroup(id: string): void;
  autoLayout(): void;
  undo(): void;
  redo(): void;
  markSaved(): void;
  setViewport(viewport: {x: number; y: number; zoom: number}): void;
  setProjectName(name: string): void;
  newWorkflow(document?: WorkflowDocument): void;
  loadWorkflow(document: WorkflowDocument, definitions?: NodeDefinition[]): void;
  serialize(): WorkflowDocument;
}

export interface ApiEvent {
  eventId?: string;
  timestamp?: string;
  type: string;
  runId?: string;
  nodeId?: string;
  payload: Record<string, any>;
}

export interface NodeRunState {
  status: string;
  progress: number;
  message?: string;
  artifactIds?: string[];
  completedAt?: string;
}

export interface RunSnapshot {
  runId: string;
  workflowId?: string;
  workflowHash?: string;
  status: string;
  priority?: number;
  queuePosition?: number | null;
  progress: number;
  nodes?: Record<string, NodeRunState>;
  artifactIds?: string[];
  error?: {code?: string; message?: string; retryable?: boolean};
}

export interface RunState {
  run: RunSnapshot | null;
  queue: {running: RunSnapshot | null; pending: RunSnapshot[]};
  history: RunSnapshot[];
  nodeStates: Record<string, NodeRunState>;
  logs: Array<{id?: string; nodeId?: string; message: string; timestamp?: string}>;
  connection: string;
  setConnection(connection: string): void;
  hydrateResults(nodes: EditorNode[]): void;
  clearResults(): void;
  clearNodeResult(nodeId: string): void;
  start(workflow: WorkflowDocument, mode?: string, selectedNodeIds?: string[], options?: {force?: boolean; queueFront?: boolean}): Promise<RunSnapshot>;
  pause(): Promise<void>;
  resume(): Promise<void>;
  cancel(runId?: string): Promise<void>;
  loadActivity(): Promise<void>;
  clearCache(): Promise<void>;
  handleEvent(event: ApiEvent): void;
}

export interface DesktopValues {
  libraryVisible: boolean;
  libraryCollapsed: boolean;
  drawerVisible: boolean;
  minimapVisible: boolean;
  settingsOpen: boolean;
  settingsSection: string;
  modelsOpen: boolean;
  drawerTab: string;
  libraryWidth: number;
  drawerHeight: number;
}

export interface DesktopState extends DesktopValues {
  setValue(key: keyof DesktopValues, value: DesktopValues[keyof DesktopValues]): void;
  toggle(key: keyof DesktopValues): void;
  reset(): void;
}

export interface ServerState {
  nodes: NodeDefinition[];
  settings: Record<string, any> | null;
  models: ModelInventory[];
  capabilities: Record<string, any> | null;
  diagnostics: Record<string, any> | null;
  downloads: DownloadQueueState;
  loading: boolean;
  error: string | null;
  bootstrap(): Promise<void>;
  refreshModels(): Promise<ModelInventory[]>;
  refreshDownloads(): Promise<DownloadQueueState>;
  setModelLifecycleState(id: string, patch: Partial<ModelInventory>): void;
  updateSettings(patch: Record<string, any>): Promise<void>;
  resetSettings(section: string): Promise<void>;
  handleEvent(event: ApiEvent): void;
}

declare global {
  interface Window {
    midgardDesktop?: MidgardDesktopApi;
  }
  const MAIN_WINDOW_VITE_DEV_SERVER_URL: string | undefined;
  const MAIN_WINDOW_VITE_NAME: string;
}
