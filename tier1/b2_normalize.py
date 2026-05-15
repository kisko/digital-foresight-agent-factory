"""B2 — Normalization & Enrichment.

Cleans text, generates a 2-sentence abstract, extracts entities, assigns
taxonomy + signal type. Emits `signal.enriched`.
"""
from __future__ import annotations

from typing import List

from shared.contracts import BaseAgent, Event, Events


class B2Normalize(BaseAgent):
    name = "b2.normalize"
    version = "0.1.0"

    def subscribes(self) -> List[str]:
        return [Events.SIGNAL_CREATED]

    async def handle(self, event: Event) -> None:
        sid = event.payload["signal_id"]
        sig = self.store.db.get_signal(sid)
        if not sig:
            return
        text = f"{sig.title}. {sig.body}"
        sig.summary     = self.llm.summarize(text)
        sig.entities    = self.llm.extract_entities(text)
        sig.taxonomy    = self.llm.classify_taxonomy(text)
        sig.signal_type = self.llm.classify_signal_type(text)
        self.store.db.upsert_signal(sig)
        await self.emit(Events.SIGNAL_ENRICHED, {"signal_id": sid}, trace_id=event.trace_id)
