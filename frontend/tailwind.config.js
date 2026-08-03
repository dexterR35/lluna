module.exports = {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        mg: {
          app: "var(--mg-bg-app)", panel: "var(--mg-bg-panel)", elevated: "var(--mg-bg-elevated)", node: "var(--mg-bg-node)",
          selected: "var(--mg-bg-node-selected)", border: "var(--mg-border)", focus: "var(--mg-border-focus)",
          primary: "var(--mg-text-primary)", secondary: "var(--mg-text-secondary)", muted: "var(--mg-text-muted)", accent: "var(--mg-accent)",
          success: "var(--mg-success)", warning: "var(--mg-warning)", error: "var(--mg-error)",
          running: "var(--mg-running)", cached: "var(--mg-cached)"
        }
      },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"] }
    }
  },
  plugins: [],
};
