"""A0 — Orchestrator / Workflow Director.

In the prototype the orchestrator is a passive observer: it watches every
event, advances a per-object state machine in memory, and exposes that view
to the dashboard via `state_for(object_id)` and `pipeline_counts()`.

It also owns the **approval gate**: insights only become `approved` when
explicitly approved through the API (which calls `approve(insight_id)`).
That separation — drafted by B5, approved by humans, then published by B6 —
is the human-in-the-loop hard gate.
"""
from __future__ import annotations

from typing import Dict, List

from shared.contracts import BaseAgent, Event, Events, Insight


PIPELINE_STAGES = [
    "signal",       # signal.created
    "enriched",     # signal.enriched
    "scored",       # signal.scored
    "clustered",    # cluster.updated (terminal for signals; cluster has own state)
    "insight",      # insight.created
    "approved",     # insight.approved
    "published",    # product.published
]


class A0Orchestrator(BaseAgent):
    name = "a0.orchestrator"
    version = "0.1.0"

    def __init__(self, bus, store, llm):
        super().__init__(bus, store, llm)
        # object_id → stage name
        self._stage: Dict[str, str] = {}
        # ordered audit trail
        self._audit: List[Dict[str, str]] = []

    def subscribes(self) -> List[str]:
        return [
            Events.SIGNAL_CREATED, Events.SIGNAL_ENRICHED, Events.SIGNAL_SCORED,
            Events.CLUSTER_UPDATED,
            Events.INSIGHT_CREATED, Events.INSIGHT_APPROVED,
            Events.PRODUCT_PUBLISHED,
            Events.AGENT_ERROR,
        ]

    async def handle(self, event: Event) -> None:
        topic = event.topic
        if topic == Events.SIGNAL_CREATED:
            self._advance(event.payload.get("signal_id"), "signal", event)
        elif topic == Events.SIGNAL_ENRICHED:
            self._advance(event.payload.get("signal_id"), "enriched", event)
        elif topic == Events.SIGNAL_SCORED:
            self._advance(event.payload.get("signal_id"), "scored", event)
        elif topic == Events.CLUSTER_UPDATED:
            self._advance(event.payload.get("cluster_id"), "clustered", event)
        elif topic == Events.INSIGHT_CREATED:
            self._advance(event.payload.get("insight_id"), "insight", event)
        elif topic == Events.INSIGHT_APPROVED:
            self._advance(event.payload.get("insight_id"), "approved", event)
        elif topic == Events.PRODUCT_PUBLISHED:
            self._advance(event.payload.get("product_id"), "published", event)
        elif topic == Events.AGENT_ERROR:
            self.log.warning(f"agent error captured: {event.payload}")

    def _advance(self, obj_id: str, stage: str, event: Event) -> None:
        if not obj_id:
            return
        self._stage[obj_id] = stage
        self._audit.append({
            "object_id": obj_id, "stage": stage,
            "agent": event.agent, "ts": event.ts,
        })

    # ── dashboard surface
    def stage_of(self, obj_id: str) -> str:
        return self._stage.get(obj_id, "unknown")

    def pipeline_counts(self) -> Dict[str, int]:
        counts = {s: 0 for s in PIPELINE_STAGES}
        for stage in self._stage.values():
            if stage in counts:
                counts[stage] += 1
        # add DB-derived "all-time" counts
        db_counts = self.store.db.counts()
        counts["_total_signals"]  = db_counts["signals"]
        counts["_total_clusters"] = db_counts["clusters"]
        counts["_total_insights"] = db_counts["insights"]
        counts["_total_products"] = db_counts["products"]
        counts["_pending_review"] = db_counts["insights_pending"]
        return counts

    def audit_tail(self, n: int = 50) -> List[Dict[str, str]]:
        return self._audit[-n:]

    # ── approval gate (called by REST API)
    async def approve(self, insight_id: str, reviewer: str = "human") -> Insight:
        i = self.store.db.get_insight(insight_id)
        if not i:
            raise KeyError(f"insight not found: {insight_id}")
        if i.status == "approved":
            return i
        i.status = "approved"
        self.store.db.upsert_insight(i)
        await self.emit(Events.INSIGHT_APPROVED, {
            "insight_id": insight_id, "reviewer": reviewer,
        })
        return i
