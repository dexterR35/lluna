import { beforeEach, expect, test } from "vitest";
import { useRunStore } from "../src/state/runStore";

beforeEach(() => {
  useRunStore.setState({
    run: null,
    nodeStates: {},
    logs: [],
  });
});

test("save progress events retain one row for every image", () => {
  const progress = useRunStore.getState().handleEvent;
  progress({
    type: "node.progress",
    nodeId: "save",
    payload: {
      progress: 0,
      itemIndex: 0,
      itemCount: 2,
      itemProgress: 0,
      itemName: "first.png",
      itemStatus: "SAVING",
      detail: "Saving to first.png",
    },
  });
  progress({
    type: "node.progress",
    nodeId: "save",
    payload: {
      progress: 50,
      itemIndex: 0,
      itemCount: 2,
      itemProgress: 100,
      itemName: "first.png",
      itemStatus: "FINISHED",
      detail: "Saved as first.png",
    },
  });
  progress({
    type: "node.progress",
    nodeId: "save",
    payload: {
      progress: 50,
      itemIndex: 1,
      itemCount: 2,
      itemProgress: 0,
      itemName: "second.png",
      itemStatus: "SAVING",
      detail: "Saving to second.png",
    },
  });

  expect(useRunStore.getState().nodeStates.save.saveItems).toEqual([
    {
      index: 0,
      name: "first.png",
      progress: 100,
      status: "FINISHED",
      detail: "Saved as first.png",
    },
    {
      index: 1,
      name: "second.png",
      progress: 0,
      status: "SAVING",
      detail: "Saving to second.png",
    },
  ]);
});

test("node.preview stores the frame without touching node status", () => {
  const handleEvent = useRunStore.getState().handleEvent;
  handleEvent({ type: "node.started", nodeId: "gen", payload: {} });
  handleEvent({
    type: "node.preview",
    nodeId: "gen",
    payload: { image: "data:image/jpeg;base64,AAAA" },
  });

  const state = useRunStore.getState().nodeStates.gen;
  expect(state.previewImage).toBe("data:image/jpeg;base64,AAAA");
  expect(state.status).toBe("RUNNING");
});

test("node.progress does not clear a preview frame just delivered", () => {
  const handleEvent = useRunStore.getState().handleEvent;
  handleEvent({ type: "node.started", nodeId: "gen", payload: {} });
  handleEvent({
    type: "node.preview",
    nodeId: "gen",
    payload: { image: "data:image/jpeg;base64,AAAA" },
  });
  handleEvent({
    type: "node.progress",
    nodeId: "gen",
    payload: { progress: 40 },
  });

  expect(useRunStore.getState().nodeStates.gen.previewImage).toBe(
    "data:image/jpeg;base64,AAAA",
  );
});

test("a fresh node.started clears a stale preview from a previous run", () => {
  const handleEvent = useRunStore.getState().handleEvent;
  handleEvent({ type: "node.started", nodeId: "gen", payload: {} });
  handleEvent({
    type: "node.preview",
    nodeId: "gen",
    payload: { image: "data:image/jpeg;base64,STALE" },
  });
  handleEvent({ type: "node.started", nodeId: "gen", payload: {} });

  expect(useRunStore.getState().nodeStates.gen.previewImage).toBeNull();
});
