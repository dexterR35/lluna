"""Lluna authenticated loopback control plane."""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
from contextlib import asynccontextmanager, suppress

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.api.auth import accept_authenticated_websocket, configure_token
from backend.api.events import EventBroker
from backend.api.routes_artifacts import router as artifacts_router
from backend.api.routes_diagnostics import router as diagnostics_router
from backend.api.routes_health import router as health_router
from backend.api.routes_health import set_ready
from backend.api.routes_models import router as models_router
from backend.api.routes_nodes import router as nodes_router
from backend.api.routes_runs import router as runs_router
from backend.api.routes_settings import router as settings_router
from backend.api.routes_workflows import router as workflows_router


def create_app(token: str | None = None) -> FastAPI:
    configure_token(token)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from backend.application.bootstrap import prepare_control_plane

        prepare_control_plane()
        set_ready(True)
        EventBroker.instance().publish("backend.ready", payload={"apiVersion": 1})
        try:
            yield
        finally:
            set_ready(False)
            from backend.graph.executor import RunManager
            from backend.models.dynamic_registry import DynamicModelRegistry
            from backend.tools.shared.download_lifecycle import abort_downloads_on_shutdown

            RunManager.instance().shutdown()
            DynamicModelRegistry.instance().stop_watcher()
            abort_downloads_on_shutdown()

    app = FastAPI(
        title="Lluna Control Plane",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["null"],
        allow_origin_regex=r"^http://(?:localhost|127\.0\.0\.1)(?::\d+)?$",
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-Lluna-Token", "Authorization"],
    )
    for router in (
        health_router,
        nodes_router,
        workflows_router,
        runs_router,
        artifacts_router,
        settings_router,
        models_router,
        diagnostics_router,
    ):
        app.include_router(router)

    @app.websocket("/api/events")
    async def events(websocket: WebSocket) -> None:
        if not await accept_authenticated_websocket(websocket):
            return
        broker = EventBroker.instance()
        queue = broker.subscribe()
        event_task = asyncio.create_task(queue.get())
        receive_task = asyncio.create_task(websocket.receive())
        try:
            while True:
                done, _pending = await asyncio.wait(
                    {event_task, receive_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if receive_task in done:
                    message = receive_task.result()
                    if message["type"] == "websocket.disconnect":
                        break
                    receive_task = asyncio.create_task(websocket.receive())
                if event_task in done:
                    event = event_task.result()
                    await websocket.send_json(event.model_dump(mode="json", by_alias=True))
                    event_task = asyncio.create_task(queue.get())
        except WebSocketDisconnect:
            pass
        finally:
            for task in (event_task, receive_task):
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            broker.unsubscribe(queue)

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lluna local control plane")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", default=os.environ.get("LLUNA_SESSION_TOKEN"))
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost"}:
        parser.error("Lluna control plane may bind only to loopback")
    token = args.token or secrets.token_urlsafe(48)
    app = create_app(token)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
