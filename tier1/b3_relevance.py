"""B3 — Relevance & Routing (The Company Lens).

Scores relevance/novelty/urgency/impact and attaches routing tags + rationale.
Lens keywords are loaded from data/sources.yaml under `company_lens`.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import yaml

from shared.contracts import BaseAgent, Event, Events


class B3Relevance(BaseAgent):
    name = "b3.relevance"
    version = "0.1.0"

    def __init__(self, bus, store, llm, sources_yaml: Path = Path("data/sources.yaml")):
        super().__init__(bus, store, llm)
        cfg = yaml.safe_load(sources_yaml.read_text()) if sources_yaml.exists() else {}
        self.lens: List[str] = (cfg.get("company_lens") or [])
        self.persona_map: dict = (cfg.get("persona_map") or {})

    def subscribes(self) -> List[str]:
        return [Events.SIGNAL_ENRICHED]

    async def handle(self, event: Event) -> None:
        sid = event.payload["signal_id"]
        sig = self.store.db.get_signal(sid)
        if not sig:
            return
        text = f"{sig.title}. {sig.summary or sig.body[:500]}"
        scores = self.llm.score_signal(text, self.lens)
        sig.relevance = scores["relevance"]
        sig.novelty   = scores["novelty"]
        sig.urgency   = scores["urgency"]
        sig.impact    = scores["impact"]
        sig.rationale = self.llm.rationale(sig.title, sig.taxonomy)
        # routing tags from taxonomy → persona map
        routing = set()
        for tax in sig.taxonomy:
            for tag in self.persona_map.get(tax, []):
                routing.add(tag)
        sig.routing = sorted(routing)
        self.store.db.upsert_signal(sig)
        await self.emit(Events.SIGNAL_SCORED, {
            "signal_id": sid, "relevance": sig.relevance,
        }, trace_id=event.trace_id)
