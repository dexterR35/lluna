const path = require("node:path");
const { builtinModules } = require("node:module");
const { defineConfig } = require("vite");

const external = ["electron", ...builtinModules, ...builtinModules.map(name => `node:${name}`)];

module.exports = defineConfig({
  define: {
    MAIN_WINDOW_VITE_DEV_SERVER_URL: JSON.stringify("http://127.0.0.1:4173"),
    MAIN_WINDOW_VITE_NAME: JSON.stringify("main_window"),
  },
  build: {
    outDir: ".e2e/build",
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: {
      external,
      input: {
        main: path.resolve(__dirname, "electron/main.js"),
        preload: path.resolve(__dirname, "electron/preload.js"),
      },
      output: {
        format: "cjs",
        entryFileNames: "[name].js",
        chunkFileNames: "[name]-[hash].js",
      },
    },
  },
});
