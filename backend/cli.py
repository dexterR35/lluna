"""Headless entry points: serve the API, or run a workflow to completion.

Two ways to drive Lluna without opening a window:

* ``lluna.py serve --port 8765 --token …`` starts the same local API the desktop
  app talks to, and nothing else. Everything the UI can do is available over HTTP
  on 127.0.0.1.
* ``lluna.py run graph.lluna.json --out ./results`` executes one workflow in this
  process and exits with a status code. No server, no token, no port — which is
  what makes it usable from a script or a cron job.

``run`` deliberately does not go through HTTP. Automation that has to start a
server, guess when it is ready, and carry a token is automation that breaks; the
executor is importable, so the CLI uses it directly.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

# Terminal statuses a run can settle into.
_FINISHED = {"COMPLETED", "FAILED", "CANCELLED"}


def _load_workflow(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"Could not read {path}: {exc}") from exc
    except ValueError as exc:
        raise SystemExit(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise SystemExit(f"{path} does not contain a workflow document.")
    return raw


def _resolve_template(name: str) -> dict[str, Any]:
    from backend.graph.templates import all_templates, get_template

    try:
        return get_template(name).document
    except KeyError:
        available = ", ".join(template.id for template in all_templates())
        raise SystemExit(f"Unknown template {name!r}. Available: {available}") from None


def run_workflow(args: argparse.Namespace) -> int:
    from backend.graph.executor import RunManager
    from backend.graph.migrations import MigrationError, migrate_workflow
    from backend.graph.schema import WorkflowDocument

    raw = _resolve_template(args.template) if args.template else _load_workflow(Path(args.workflow))
    try:
        document, applied = migrate_workflow(raw)
    except MigrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for step in applied:
        print(f"migrated {step}")

    try:
        workflow = WorkflowDocument.model_validate(document)
    except Exception as exc:  # pydantic raises its own error type
        print(f"error: this workflow is not valid: {exc}", file=sys.stderr)
        return 2

    manager = RunManager.instance()
    snapshot = manager.start(workflow, force=args.force)
    print(f"run {snapshot.run_id} started ({len(workflow.nodes)} nodes)")

    deadline = time.monotonic() + args.timeout
    last_progress = -1
    while True:
        snapshot = manager.get(snapshot.run_id)
        if snapshot.progress != last_progress and not args.quiet:
            last_progress = snapshot.progress
            print(f"  {snapshot.status.lower()} {snapshot.progress}%", flush=True)
        if snapshot.status in _FINISHED:
            break
        if time.monotonic() > deadline:
            manager.cancel(snapshot.run_id)
            print(f"error: timed out after {args.timeout}s", file=sys.stderr)
            return 3
        time.sleep(0.25)

    if snapshot.status != "COMPLETED":
        error = snapshot.error or {}
        print(
            f"error: run {snapshot.status.lower()}: "
            f"{error.get('message') or 'no detail reported'}",
            file=sys.stderr,
        )
        return 1

    written = _collect_artifacts(snapshot, args.out)
    for path in written:
        print(f"wrote {path}")
    if not written and not args.quiet:
        print("run completed; no artifacts were produced")
    return 0


def _collect_artifacts(snapshot: Any, destination: str | None) -> list[Path]:
    """Copy the run's artifacts out of internal storage, if asked to."""
    if not destination:
        return []
    from backend.artifacts.store import ArtifactStore

    out = Path(destination).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    store = ArtifactStore.instance()
    written: list[Path] = []
    # Several nodes can carry the same artifact forward (a passthrough preview,
    # for instance), so the run lists it more than once. Export each file once,
    # in first-seen order.
    for artifact_id in dict.fromkeys(snapshot.artifact_ids):
        try:
            artifact = store.get(artifact_id)
            source = Path(artifact.path)
            target = out / f"{artifact_id}{source.suffix}"
            shutil.copy2(source, target)
            written.append(target)
        except (KeyError, OSError) as exc:
            print(f"warning: could not export {artifact_id}: {exc}", file=sys.stderr)
    return written


def list_templates(args: argparse.Namespace) -> int:
    from backend.graph.templates import all_templates

    templates = all_templates()
    if args.json:
        print(json.dumps([template.to_dict() for template in templates], indent=2))
        return 0
    width = max(len(template.id) for template in templates)
    for template in templates:
        print(f"{template.id:<{width}}  {template.name} — {template.description}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lluna",
        description="Lluna: local node-based image and video AI workflows.",
    )
    subcommands = parser.add_subparsers(dest="command")

    serve = subcommands.add_parser("serve", help="Run the local API without the desktop app.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, required=True)
    serve.add_argument("--token", default=None)

    run = subcommands.add_parser("run", help="Execute one workflow and exit.")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("workflow", nargs="?", help="Path to a .lluna.json workflow.")
    source.add_argument("--template", help="Run a bundled template by id instead.")
    run.add_argument("--out", help="Directory to copy produced artifacts into.")
    run.add_argument(
        "--timeout", type=float, default=3600.0, help="Seconds before the run is cancelled."
    )
    run.add_argument("--force", action="store_true", help="Ignore cached node results.")
    run.add_argument("--quiet", action="store_true", help="Only report failures and outputs.")
    run.set_defaults(handler=run_workflow)

    templates = subcommands.add_parser("templates", help="List bundled workflow templates.")
    templates.add_argument("--json", action="store_true", help="Emit the full documents as JSON.")
    templates.set_defaults(handler=list_templates)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Without a subcommand, fall through to the server so existing launchers
    # (the desktop app, packaging scripts) keep working unchanged.
    if not argv or argv[0].startswith("-"):
        from backend.api.app import main as serve_main

        return serve_main(argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        from backend.api.app import main as serve_main

        forwarded = ["--host", args.host, "--port", str(args.port)]
        if args.token:
            forwarded += ["--token", args.token]
        return serve_main(forwarded)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1
    return int(handler(args))
