const { defineConfig } = require("vite");
const react = require("@vitejs/plugin-react");
const tailwindcss = require("@tailwindcss/vite").default;

module.exports = defineConfig({
  plugins: [tailwindcss(), react.default()],
  root: __dirname,
  build: { outDir: "dist", emptyOutDir: true, sourcemap: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.js"],
    globals: true,
  },
});
