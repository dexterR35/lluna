import { Component } from "react";
import { Button } from "./Button";
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
          className="grid h-screen place-items-center bg-mg-app p-8"
        >
          <div className="max-w-lg rounded-mg-lg border border-mg-error/50 bg-mg-panel p-6 shadow-soft">
            <h1 className="text-[15px] font-semibold tracking-tight text-mg-primary">
              The editor hit an unexpected error
            </h1>
            <p className="mt-2 text-sm text-mg-secondary">
              {this.state.error.message}
            </p>
            <Button className="mt-5" onClick={() => location.reload()}>
              Restart renderer
            </Button>
          </div>
        </div>
      );
    return this.props.children;
  }
}
