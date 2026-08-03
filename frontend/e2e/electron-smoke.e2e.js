const path = require("node:path");
const { test, expect, _electron: electron } = require("@playwright/test");

let electronApp;

test.beforeAll(async () => {
  electronApp = await electron.launch({
    args: ["--no-sandbox", path.resolve(__dirname, "../.e2e/build/main.js")],
    cwd: path.resolve(__dirname, ".."),
    env: { ...process.env, MIDGARD_E2E: "1" },
    timeout: 30_000,
  });
});

test.afterAll(async () => {
  await electronApp?.close();
});

test("Electron starts its control plane and renders the backend-owned node catalog", async () => {
  const page = await electronApp.firstWindow();
  await expect(page).toHaveTitle("Midgard");
  await expect(page.getByRole("button", { name: "Run" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Load Image/ })).toBeVisible();
  await expect(page.getByText("Backend connected", { exact: true })).toBeVisible();

  const security = await electronApp.evaluate(({ BrowserWindow }) => {
    const window = BrowserWindow.getAllWindows()[0];
    return window.webContents.getLastWebPreferences();
  });
  expect(security.nodeIntegration).toBe(false);
  expect(security.contextIsolation).toBe(true);
  expect(security.sandbox).toBe(true);
  expect(security.webSecurity).toBe(true);
});
