import { createContext, useContext } from "react";

/**
 * Per-node action callbacks and the model inventory, provided once by
 * WorkflowCanvas instead of being threaded through every node's xyflow
 * `data` prop. Putting these on `data` meant a brand-new object was
 * allocated for every node on every graph mutation (new callback identity
 * or not), which defeated LlunaNode's `memo()` and forced a full re-render
 * of every node card on any single-node edit. Context lets LlunaNode read
 * them without that per-node `data` churn, so `memo()` actually works.
 * @typedef {{onOpen?: (id: string) => void, onRun?: (id: string) => void, onPreview?: (id: string) => void, onModelChange?: (id: string, value: string | number) => void, onParameterChange?: (id: string, key: string, value: unknown) => void}} NodeActions
 */

/** @type {import("react").Context<{actions: NodeActions, modelInventory: import("../types").ModelInventory[]}>} */
const NodeActionsContext = createContext({
  actions: /** @type {NodeActions} */ ({}),
  modelInventory: /** @type {import("../types").ModelInventory[]} */ ([]),
});

export const NodeActionsProvider = NodeActionsContext.Provider;

export function useNodeActionsContext() {
  return useContext(NodeActionsContext);
}
