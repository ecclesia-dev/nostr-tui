"""WebSocket relay manager — connects to relays, subscribes, publishes."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

import websockets
import websockets.asyncio.client

log = logging.getLogger(__name__)


@dataclass
class RelayMessage:
    relay_url: str
    data: Any


EventCallback = Callable[[RelayMessage], Coroutine[Any, Any, None]]


class RelayPool:
    """Manages connections to multiple Nostr relays."""

    def __init__(self, relay_urls: list[str]) -> None:
        self.relay_urls = relay_urls
        self._connections: dict[str, websockets.asyncio.client.ClientConnection] = {}
        self._tasks: list[asyncio.Task] = []
        self._callbacks: list[EventCallback] = []
        self._running = False

    def on_event(self, callback: EventCallback) -> None:
        self._callbacks.append(callback)

    async def _handle_relay(self, url: str) -> None:
        """Connect to a single relay, reconnecting on failure."""
        while self._running:
            try:
                async with websockets.asyncio.client.connect(url) as ws:
                    self._connections[url] = ws
                    log.info("Connected to %s", url)
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        msg = RelayMessage(relay_url=url, data=data)
                        for cb in self._callbacks:
                            try:
                                await cb(msg)
                            except Exception:
                                log.exception("Callback error for %s", url)
            except Exception:
                log.warning("Relay %s disconnected, reconnecting in 5s...", url)
                self._connections.pop(url, None)
                await asyncio.sleep(5)

    async def connect(self) -> None:
        """Start connections to all relays."""
        self._running = True
        for url in self.relay_urls:
            task = asyncio.create_task(self._handle_relay(url))
            self._tasks.append(task)

    async def close(self) -> None:
        """Close all relay connections."""
        self._running = False
        for ws in self._connections.values():
            await ws.close()
        self._connections.clear()
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    async def subscribe(self, filters: dict) -> str:
        """Send a REQ to all connected relays. Returns the subscription id."""
        sub_id = uuid.uuid4().hex[:16]
        req = json.dumps(["REQ", sub_id, filters], separators=(",", ":"))
        await self._send_all(req)
        return sub_id

    async def publish(self, event_json: str) -> None:
        """Publish a signed event to all connected relays."""
        await self._send_all(event_json)

    async def _send_all(self, msg: str) -> None:
        for url, ws in list(self._connections.items()):
            try:
                await ws.send(msg)
            except Exception:
                log.warning("Failed to send to %s", url)

    async def wait_connected(self, timeout: float = 10.0) -> bool:
        """Wait until at least one relay is connected."""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if self._connections:
                return True
            await asyncio.sleep(0.2)
        return bool(self._connections)
