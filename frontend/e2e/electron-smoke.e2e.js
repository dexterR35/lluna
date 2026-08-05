const path = require("node:path");
const { test, expect, _electron: electron } = require("@playwright/test");

let electronApp;

test.beforeAll(async () => {
  electronApp = await electron.launch({
    args: ["--no-sandbox", path.resolve(__dirname, "../.e2e/build/main.js")],
    cwd: path.resolve(__dirname, ".."),
    env: { ...process.env, LLUNA_E2E: "1" },
    timeout: 30_000,
  });
});

test.afterAll(async () => {
  await electronApp?.close();
});

test("Electron starts its control plane and renders the backend-owned node catalog", async () => {
  const page = await electronApp.firstWindow();
  await expect(page).toHaveTitle("Lluna");
  await expect(page.getByRole("button", { name: "Run" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Load Image/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Inspector", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Boolean\b/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Integer\b/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Number\b/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Show Metadata\b/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Workflow Note\b/ })).toHaveCount(0);
  await expect(page.getByText("Backend ready", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /Upscale Image/ }).click();
  const upscaleNode = page.getByLabel("Upscale Image node");
  await expect(upscaleNode.getByRole("button", { name: "Run from here Upscale Image" })).toBeVisible();
  const viewport = page.locator(".react-flow__viewport");
  await expect(viewport).toHaveAttribute("style", /scale\(0\.85\)/);
  const nodeBoxBeforeZoom = await upscaleNode.boundingBox();
  const zoomPoint = { x: nodeBoxBeforeZoom.x + nodeBoxBeforeZoom.width / 2, y: nodeBoxBeforeZoom.y + nodeBoxBeforeZoom.height / 2 };
  await page.mouse.move(zoomPoint.x, zoomPoint.y);
  await page.mouse.wheel(0, -240);
  await page.waitForTimeout(150);
  await expect(viewport).toHaveAttribute("style", /scale\(0\.85\)/);
  await page.keyboard.down("Control");
  await page.mouse.wheel(0, -240);
  await page.keyboard.up("Control");
  await expect.poll(async () => Number((await viewport.getAttribute("style")).match(/scale\(([^)]+)\)/)?.[1])).toBeGreaterThan(0.85);
  const nodeBoxAfterZoom = await upscaleNode.boundingBox();
  expect(Math.abs(nodeBoxAfterZoom.x + nodeBoxAfterZoom.width / 2 - zoomPoint.x)).toBeLessThan(3);
  expect(Math.abs(nodeBoxAfterZoom.y + nodeBoxAfterZoom.height / 2 - zoomPoint.y)).toBeLessThan(3);
  const scaleBeforeDoubleClick = (await viewport.getAttribute("style")).match(/scale\(([^)]+)\)/)?.[1];
  await upscaleNode.dblclick();
  await page.waitForTimeout(350);
  const scaleAfterDoubleClick = (await viewport.getAttribute("style")).match(/scale\(([^)]+)\)/)?.[1];
  expect(scaleAfterDoubleClick).toBe(scaleBeforeDoubleClick);
  const canvas = page.locator(".react-flow");
  const canvasBox = await canvas.boundingBox();
  const transformBeforePan = await viewport.getAttribute("style");
  await page.keyboard.down("Space");
  await expect(canvas).toHaveClass(/artboard-panning/);
  await page.mouse.move(canvasBox.x + 40, canvasBox.y + 60);
  await page.mouse.down();
  await page.mouse.move(canvasBox.x + 100, canvasBox.y + 100, { steps: 4 });
  await page.mouse.up();
  await page.keyboard.up("Space");
  await expect.poll(async () => viewport.getAttribute("style")).not.toBe(transformBeforePan);
  await expect(page.getByRole("dialog", { name: "Upscale Image" })).toHaveCount(0);
  await upscaleNode.getByRole("button", { name: "Open Upscale Image options" }).click();
  const nodeEditor = page.getByRole("dialog", { name: "Upscale Image" });
  await expect(nodeEditor.getByRole("button", { name: /Real-ESRGAN ×2/ })).toBeVisible();
  await nodeEditor.getByRole("button", { name: /Real-ESRGAN ×4/ }).click();
  await nodeEditor.getByRole("button", { name: "Done" }).click();
  await expect(page.getByLabel("Upscale Image node").getByText("Real-ESRGAN ×4")).toBeVisible();

  const security = await electronApp.evaluate(({ BrowserWindow }) => {
    const window = BrowserWindow.getAllWindows()[0];
    return window.webContents.getLastWebPreferences();
  });
  expect(security.nodeIntegration).toBe(false);
  expect(security.contextIsolation).toBe(true);
  expect(security.sandbox).toBe(true);
  expect(security.webSecurity).toBe(true);
});
