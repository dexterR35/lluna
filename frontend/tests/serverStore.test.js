import { beforeEach, expect, test } from "vitest";
import { useServerStore } from "../src/state/serverStore";

beforeEach(() => {
  useServerStore.setState({ downloads: { active: [], pending: [] } });
});

test("download queue events preserve active progress and FIFO positions", () => {
  useServerStore.getState().handleEvent({
    type: "download.queue.updated",
    payload: {
      active: [
        {
          jobId: 11,
          kind: "model",
          key: "realesrgan-x2",
          modelId: "realesrgan-x2",
          operation: "install",
          state: "active",
          position: 0,
          progress: 46,
        },
      ],
      pending: [
        {
          jobId: 12,
          kind: "model",
          key: "realesrgan-x4",
          modelId: "realesrgan-x4",
          operation: "install",
          state: "queued",
          position: 1,
          progress: null,
        },
      ],
    },
  });

  const downloads = useServerStore.getState().downloads;
  expect(downloads.active[0]).toMatchObject({ progress: 46, position: 0 });
  expect(downloads.pending[0]).toMatchObject({ position: 1, state: "queued" });
});
