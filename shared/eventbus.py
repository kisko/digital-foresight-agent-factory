"""In-process pub/sub event bus.

Production swap-in: replace with `ServiceBusEventBus` that publishes to Azure
Service Bus topics. The interface (subscribe/publish/history) stays identical.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from typing import Awaitable, Callable, Deque, Dict, List

from shared.contracts import Event

log = logging.getLogger("eventbus")

Handler = Callable[[Event], Awaitable[None]]


class InProcessEventBus:
    def __init__(self, history_size: int = 500):
        self._subs: Dict[str, List[Handler]] = defaultdict(list)
        self._history: Deque[Event] = deque(maxlen=history_size)
        # listeners for the dashboard (every event, regardless of topic)
        self._tap: List[Callable[[Event], None]] = []

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._subs[topic].append(handler)

    def tap(self, fn: Callable[[Event], None]) -> Callable[[], None]:
        """Register a fire-and-forget listener for every event (dashboard use)."""
        self._tap.append(fn)
        def unsubscribe():
            if fn in self._tap:
                self._tap.remove(fn)
        return unsubscribe

    async def publish(self, event: Event) -> None:
        self._history.append(event)
        log.debug(f"PUB {event.topic} by {event.agent}")
        for fn in self._tap:
            try:
                fn(event)
            except Exception:
                log.exception("tap listener failed")
        # Schedule handlers concurrently; don't block the publisher.
        handlers = self._subs.get(event.topic, [])
        if not handlers:
            return
        # Fire each handler as its own task so one slow handler doesn't stall.
        for h in handlers:
            asyncio.create_task(h(event))

    def history(self, limit: int = 100) -> List[Event]:
        return list(self._history)[-limit:]

    def stats(self) -> Dict[str, int]:
        counts: Dict[str, int] = defaultdict(int)
        for ev in self._history:
            counts[ev.topic] += 1
        return dict(counts)


# module-level singleton (the prototype uses one bus)
_bus: InProcessEventBus | None = None


def get_bus() -> InProcessEventBus:
    global _bus
    if _bus is None:
        _bus = InProcessEventBus()
    return _bus
