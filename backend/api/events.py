"""Versioned event envelopes and WebSocket fan-out."""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class EventEnvelope(BaseModel):
    model_config = ConfigDict(
        alias_generator=lambda value: value.split("_")[0]
        + "".join(part.title() for part in value.split("_")[1:]),
        populate_by_name=True,
    )
    version: int = 1
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    type: str
    run_id: str | None = None
    node_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class EventBroker:
    _instance: "EventBroker | None" = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()
        self._lock = threading.RLock()

    @classmethod
    def instance(cls) -> "EventBroker":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def publish(
        self,
        type: str,
        *,
        run_id: str | None = None,
        node_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> EventEnvelope:
        event = EventEnvelope(type=type, run_id=run_id, node_id=node_id, payload=payload or {})
        with self._lock:
            subscribers = tuple(self._subscribers)
        for loop, queue in subscribers:
            if loop.is_closed():
                continue
            loop.call_soon_threadsafe(self._put, queue, event)
        return event

    @staticmethod
    def _put(queue: asyncio.Queue, event: EventEnvelope) -> None:
        if queue.qsize() >= 1000:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait(event)

    def subscribe(self) -> asyncio.Queue:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.add((loop, queue))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers = {item for item in self._subscribers if item[1] is not queue}
