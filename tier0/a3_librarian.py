"""A3 — Knowledge Store Librarian.

In the prototype, the Librarian is essentially a façade over `shared.store`.
It maintains the vector index incrementally as new signals arrive and exposes
`retrieval_pack(cluster_id)` for B5.
"""
from __future__ import annotations

from typing import List

from shared.contracts import BaseAgent, Event, Events


class A3Librarian(BaseAgent):
    name = "a3.librarian"
    version = "0.1.0"

    def subscribes(self) -> List[str]:
        return [Events.SIGNAL_CREATED, Events.SIGNAL_ENRICHED]

    async def handle(self, event: Event) -> None:
        sid = event.payload.get("signal_id")
        if not sid:
            return
        sig = self.store.db.get_signal(sid)
        if not sig:
            return
        text = f"{sig.title}\n{sig.summary or sig.body[:500]}"
        self.store.vec.add(sid, text)
