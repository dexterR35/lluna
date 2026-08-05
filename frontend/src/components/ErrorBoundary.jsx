import { Component } from "react";
import { Button } from "./Button";
import { IconButton } from "./IconButton";
import { X } from "../icons";

/** @extends {Component<{children?: import("react").ReactNode}, {error: Error | null}>} */
export class ErrorBoundary extends Component {
  state = { error: /** @type {Error | null} */ (null) };
  static getDerivedStateFromError(/** @type {Error} */ error) {
    return { error };
  }
  componentDidCatch(
    /** @type {Error} */ error,
    /** @type {import("react").ErrorInfo} */ info,
  ) {
    console.error("Renderer failure", error, info);
  }
  render() {
    if (this.state.error)
      return (
        <div
          role="alert"
          className="grid h-screen place-items-center bg-mg-app p-6"
        >
          <section className="w-full max-w-xl overflow-hidden rounded-mg-lg border border-mg-border bg-mg-panel">
            <header className="ui-preview-bar is-header h-auto items-start justify-between gap-3 px-4 py-3.5">
              <div className="min-w-0">
                <h1 className="ui-copy-title">
                  The editor hit an unexpected error
                </h1>
                <p className="ui-copy-body mt-1 leading-5">
                  {this.state.error.message}
                </p>
              </div>
              <IconButton
                label="Reload renderer"
                onClick={() => location.reload()}
              >
                <X className="ui-icon" />
              </IconButton>
            </header>
            <footer className="ui-actions ui-rule justify-end bg-mg-app/40 p-3">
              <Button onClick={() => location.reload()}>Restart renderer</Button>
            </footer>
          </section>
        </div>
      );
    return this.props.children;
  }
}
