import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useServerStore } from "../src/state/serverStore";

beforeEach(() => {
  useServerStore.setState({ downloads: { active: [], pending: [], recent: [] } });
});

afterEach(() => {
  vi.unstubAllGlobals();
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
      recent: [
        {
          jobId: 10,
          kind: "model",
          key: "mirnet",
          modelId: "mirnet",
          operation: "install",
          state: "failed",
          position: -1,
          error: "network unavailable",
        },
      ],
    },
  });

  const downloads = useServerStore.getState().downloads;
  expect(downloads.active[0]).toMatchObject({ progress: 46, position: 0 });
  expect(downloads.pending[0]).toMatchObject({ position: 1, state: "queued" });
  expect(downloads.recent[0]).toMatchObject({
    state: "failed",
    error: "network unavailable",
  });
});

test("cancelling an installation shows rollback state and refreshes the queue", async () => {
  const finished = {
    active: [],
    pending: [],
    recent: [
      {
        jobId: 31,
        kind: "model",
        key: "mirnet",
        operation: "install",
        state: "cancelled",
        position: -1,
      },
    ],
  };
  const fetch = vi
    .fn()
    .mockResolvedValueOnce({
      ok: true,
      status: 202,
      json: async () => ({ cancelRequested: true }),
    })
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => finished,
    });
  vi.stubGlobal("fetch", fetch);
  useServerStore.setState({
    downloads: {
      active: [
        {
          jobId: 31,
          kind: "model",
          key: "mirnet",
          operation: "install",
          state: "active",
          position: 0,
          progress: 42,
        },
      ],
      pending: [],
      recent: [],
    },
  });

  const cancelling = useServerStore.getState().cancelDownload(31);
  expect(useServerStore.getState().downloads.active[0]).toMatchObject({
    state: "stopping",
    detail: "Cancelling and rolling back installation…",
  });
  await cancelling;

  expect(fetch).toHaveBeenNthCalledWith(
    1,
    expect.stringContaining("/api/downloads/31/cancel"),
    expect.objectContaining({ method: "POST" }),
  );
  expect(useServerStore.getState().downloads).toEqual(finished);
});
