import { act, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { ToastProvider } from "../src/components";
import { NodePreviewDialog } from "../src/nodes/NodePreviewDialog";
import { useEditorStore } from "../src/state/editorStore";
import { useRunStore } from "../src/state/runStore";

const preview = vi.hoisted(() =>
  /** @type {{props: any}} */ ({ props: null }),
);

vi.mock("../src/preview/ArtifactPreview", () => ({
  ArtifactPreview: (/** @type {any} */ props) => {
    preview.props = props;
    return <div aria-label="Mock artifact preview" />;
  },
  ArtifactThumbnail: () => <div />,
}));

beforeEach(() => {
  preview.props = null;
  useRunStore.setState({ nodeStates: {} });
  useEditorStore.setState({
    nodes: [
      {
        id: "source-video",
        type: "lluna",
        position: { x: 0, y: 0 },
        data: {
          schemaId: "lluna.input.video",
          schemaVersion: 1,
          label: "Original Video",
          parameters: {},
          appearance: {},
          result: { status: "READY", artifactIds: ["original-artifact"] },
        },
      },
      {
        id: "remove-text",
        type: "lluna",
        position: { x: 200, y: 0 },
        data: {
          schemaId: "lluna.video.remove_text",
          schemaVersion: 1,
          label: "Remove Text",
          parameters: { subAreas: [] },
          appearance: {},
          result: { status: "FAILED", artifactIds: ["stale-output"] },
          definition: {
            schemaId: "lluna.video.remove_text",
            schemaVersion: 1,
            name: "Remove Text",
            supportsPreview: true,
            inputs: [{ id: "video", label: "Video", type: "VIDEO" }],
            outputs: [{ id: "video", label: "Video", type: "VIDEO" }],
            parameters: [
              { id: "subAreas", label: "Removal areas", type: "json" },
            ],
          },
        },
      },
    ],
    edges: [
      {
        id: "video-edge",
        source: "source-video",
        sourceHandle: "video",
        target: "remove-text",
        targetHandle: "video",
        type: "lluna",
      },
    ],
    groups: [],
  });
});

test("remove-text preview uses the original video and saves drawn areas", () => {
  render(
    <ToastProvider>
      <NodePreviewDialog
        nodeId="remove-text"
        onClose={vi.fn()}
        onRun={vi.fn()}
      />
    </ToastProvider>,
  );

  expect(screen.getByText("Original source video")).toBeInTheDocument();
  expect(preview.props.artifactId).toBe("original-artifact");
  expect(preview.props.saveable).toBe(false);

  act(() => preview.props.onSubtitleAreaAdd([100, 200, 300, 400]));
  const target = useEditorStore
    .getState()
    .nodes.find((node) => node.id === "remove-text");
  if (!target) throw new Error("Expected remove-text node");
  expect(target.data.parameters.subAreas).toEqual([[100, 200, 300, 400]]);
});
