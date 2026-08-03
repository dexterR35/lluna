const { defineConfig } = require("vite");
const react = require("@vitejs/plugin-react");
module.exports = defineConfig({
  plugins: [react.default()],
  root: __dirname,
  build: { outDir: "dist", emptyOutDir: true, sourcemap: true },
  test: { environment: "jsdom", setupFiles: ["./tests/setup.js"], globals: true },
});
