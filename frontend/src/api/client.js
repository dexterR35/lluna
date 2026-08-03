import { z } from "zod";

const SessionSchema = z.object({
  baseUrl: z.string().url(),
  token: z.string().min(32),
});
/** @type {{baseUrl: string, token: string} | null} */
let session = null;

export async function initializeApi() {
  if (session) return session;
  const desktop = window.midgardDesktop;
  if (desktop) {
    session = SessionSchema.parse(await desktop.getBackendSession());
  } else {
    session = SessionSchema.parse({
      baseUrl: import.meta.env.VITE_MIDGARD_API_URL || "http://127.0.0.1:8765",
      token:
        import.meta.env.VITE_MIDGARD_TOKEN ||
        "midgard-development-token-000000000000000000",
    });
  }
  return session;
}

/** @typedef {Omit<RequestInit, "headers"> & {headers?: Record<string, string>}} ApiOptions */
/** @param {string} path @param {ApiOptions} [options] @returns {Promise<any>} */
export async function api(path, options = {}) {
  const current = await initializeApi();
  const response = await fetch(`${current.baseUrl}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Midgard-Token": current.token,
      ...options.headers,
    },
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      detail =
        typeof payload.detail === "string"
          ? payload.detail
          : payload.detail?.message || JSON.stringify(payload.detail);
    } catch {
      /* Response may not contain JSON. */
    }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

/** @param {string} artifactId */
export async function artifactObjectUrl(artifactId) {
  const current = await initializeApi();
  const response = await fetch(
    `${current.baseUrl}/api/artifacts/${artifactId}`,
    { headers: { "X-Midgard-Token": current.token } },
  );
  if (!response.ok) throw new Error("Artifact is unavailable");
  return URL.createObjectURL(await response.blob());
}

/** @param {string} artifactId @param {string} destinationGrantId */
export async function saveArtifact(artifactId, destinationGrantId) {
  return api(`/api/artifacts/${artifactId}/save`, {
    method: "POST",
    body: JSON.stringify({ destinationGrantId }),
  });
}

/** @param {(event: import("../types").ApiEvent) => void} onEvent @param {(state: string) => void} [onState] */
export async function connectEvents(onEvent, onState) {
  const current = await initializeApi();
  let stopped = false,
    retry = 300;
  /** @type {WebSocket | null} */
  let activeSocket = null;
  async function connect() {
    if (stopped) return;
    onState?.("connecting");
    const wsUrl = current.baseUrl.replace(/^http/, "ws");
    const socket = new WebSocket(
      `${wsUrl}/api/events?token=${encodeURIComponent(current.token)}`,
    );
    activeSocket = socket;
    socket.addEventListener("open", () => {
      retry = 300;
      onState?.("connected");
    });
    socket.addEventListener("message", (message) => {
      try {
        onEvent(JSON.parse(String(message.data)));
      } catch (error) {
        console.error("Invalid backend event", error);
      }
    });
    socket.addEventListener("close", () => {
      if (activeSocket === socket) activeSocket = null;
      onState?.("disconnected");
      if (!stopped) setTimeout(connect, (retry = Math.min(retry * 2, 5000)));
    });
    socket.addEventListener("error", () => socket.close());
  }
  await connect();
  return () => {
    stopped = true;
    activeSocket?.close();
    activeSocket = null;
  };
}
