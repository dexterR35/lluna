const path = require("node:path");
const { execFile } = require("node:child_process");
const { mkdir, rename } = require("node:fs/promises");
const { promisify } = require("node:util");
const { VitePlugin } = require("@electron-forge/plugin-vite");

// extract-zip can abandon Electron archives on some Linux hosts. Packager reads
// this exported function at call time, so use the platform archive utility.
const packagerUnzip = require("@electron/packager/dist/unzip");
const execFileAsync = promisify(execFile);
packagerUnzip.extractElectronZip = async (zipPath, targetDir) => {
  await mkdir(targetDir, { recursive: true });
  const executable = process.platform === "win32" ? "tar.exe" : "unzip";
  const args = process.platform === "win32" ? ["-xf", zipPath, "-C", targetDir] : ["-q", zipPath, "-d", targetDir];
  await execFileAsync(executable, args);
};

module.exports = {
  packagerConfig: {
    name: "Lluna",
    asar: true,
    executableName: "Lluna",
    icon: path.resolve(__dirname, "assets", "app-icon", "lluna"),
    electronZipDir: process.env.LLUNA_ELECTRON_ZIP_DIR || undefined,
    extraResource: [
      path.resolve(__dirname, "..", "build", "backend-sidecar", "lluna-backend"),
      path.resolve(__dirname, "assets", "app-icon"),
    ],
    afterCopyExtraResources: [
      (/** @type {string} */ buildPath, /** @type {string} */ _electronVersion, /** @type {string} */ _platform, /** @type {string} */ _arch, /** @type {(error?: unknown) => void} */ done) => {
        const resourcesPath = path.join(buildPath, "resources");
        rename(path.join(resourcesPath, "lluna-backend"), path.join(resourcesPath, "backend-sidecar")).then(() => done(), done);
      },
    ],
  },
  rebuildConfig: {},
  makers: [
    { name: "@electron-forge/maker-squirrel", config: { name: "Lluna" } },
    { name: "@electron-forge/maker-zip", platforms: ["darwin", "linux", "win32"] },
    { name: "@electron-forge/maker-dmg", config: {} },
    { name: "@electron-forge/maker-deb", config: { options: { maintainer: "Lluna", homepage: "https://github.com/dexterR35/lluna" } } },
  ],
  plugins: [
    new VitePlugin({
      build: [
        { entry: "electron/main.js", config: "vite.main.config.js", target: "main" },
      ],
      renderer: [{ name: "main_window", config: "vite.renderer.config.js" }],
    }),
  ],
};
