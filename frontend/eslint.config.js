const js = require("@eslint/js");
const globals = require("globals");
const reactHooks = require("eslint-plugin-react-hooks");
const reactRefresh = require("eslint-plugin-react-refresh");
const react = require("eslint-plugin-react");
module.exports = [
  { ignores: ["dist", ".vite", "out"] },
  js.configs.recommended,
  { files: ["src/**/*.{js,jsx}", "tests/**/*.{js,jsx}"], languageOptions: { ecmaVersion: 2022, sourceType: "module", parserOptions: { ecmaFeatures: { jsx: true } }, globals: { ...globals.browser, ...globals.es2022 } }, plugins: { react, "react-hooks": reactHooks, "react-refresh": reactRefresh }, rules: { "react/jsx-uses-vars": "error", "react/jsx-uses-react": "off", ...reactHooks.configs.recommended.rules, ...reactRefresh.configs.vite.rules, "no-unused-vars": ["error", { argsIgnorePattern: "^_" }] } },
  { files: ["electron/**/*.js"], languageOptions: { ecmaVersion: 2022, sourceType: "module", globals: { ...globals.node } } },
  { files: ["*.config.js"], languageOptions: { ecmaVersion: 2022, sourceType: "commonjs", globals: { ...globals.node } } },
];
