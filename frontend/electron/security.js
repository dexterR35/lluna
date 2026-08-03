import { shell, session } from "electron";

const EXTERNAL_URLS = Object.freeze({
  documentation: "https://github.com/dexterR35/midgard#readme",
  homepage: "https://github.com/dexterR35/midgard",
  releases: "https://github.com/dexterR35/midgard/releases",
  issues: "https://github.com/dexterR35/midgard/issues",
});

/** @param {string} rawUrl @param {string | undefined} devServerUrl */
function isLocalRendererUrl(rawUrl, devServerUrl) {
  try {
    const url = new URL(rawUrl);
    if (devServerUrl && url.origin === new URL(devServerUrl).origin) return true;
    return url.protocol === "file:";
  } catch {
    return false;
  }
}

/** @param {import("electron").BrowserWindow} window @param {string | undefined} devServerUrl */
function installWindowSecurity(window, devServerUrl) {
  window.webContents.setWindowOpenHandler(({ url }) => {
    const approved = Object.values(EXTERNAL_URLS).some(value => value === url);
    if (approved) void shell.openExternal(url);
    return { action: "deny" };
  });
  window.webContents.on("will-navigate", (event, url) => {
    if (!isLocalRendererUrl(url, devServerUrl)) event.preventDefault();
  });
  window.webContents.on("will-attach-webview", (event) => event.preventDefault());
}

/** @param {string | undefined} devServerUrl */
function installContentSecurityPolicy(devServerUrl) {
  const scriptSource = devServerUrl ? "script-src 'self' 'unsafe-inline'" : "script-src 'self'";
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        "Content-Security-Policy": [
          `default-src 'self'; ${scriptSource}; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: http://127.0.0.1:*; media-src 'self' blob: http://127.0.0.1:*; connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:* http://localhost:* ws://localhost:*; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'`,
        ],
      },
    });
  });
}

/** @param {keyof typeof EXTERNAL_URLS} id */
async function openApprovedExternal(id) {
  const url = EXTERNAL_URLS[id];
  if (!url) throw new Error("Unknown external URL identifier");
  await shell.openExternal(url);
}

export { installWindowSecurity, installContentSecurityPolicy, openApprovedExternal };
