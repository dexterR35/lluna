const path = require("node:path");
const { defineConfig } = require("vite");

module.exports = defineConfig({
  build: {
    lib: false,
    sourcemap: true,
    rollupOptions: {
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
