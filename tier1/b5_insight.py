"""B5 — Insight Drafting (So-What for The Company).

Triggers on cluster.updated. When a cluster has at least 2 signals AND no
existing insight, drafts one using the standard template (what happened,
evidence, implications, time horizon, uncertainties, actions).
"""
from __future__ import annotations

from typing import List, Optional

from shared.contracts import BaseAgent, Event, Events, Insight
from shared.ids import new_id

MIN_CLUSTER_SIZE = 2


class B5Insight(BaseAgent):
    name = "b5.insight"
    version = "0.1.0"

    def subscribes(self) -> List[str]:
        return [Events.CLUSTER_UPDATED]

    async def handle(self, event: Event) -> None:
        cid = event.payload["cluster_id"]
        cl = self.store.db.get_cluster(cid)
        if not cl or len(cl.signal_ids) < MIN_CLUSTER_SIZE:
            return
        # skip if this cluster already has an insight in 'draft' or 'approved'
        existing = [i for i in self.store.db.list_insights() if i.cluster_id == cid]
        if any(i.status in {"draft", "approved", "published"} for i in existing):
            return
        sigs = self.store.retrieval_pack(cid, k=5)
        if not sigs:
            return
        all_taxonomy = sorted({t for s in sigs for t in (s.taxonomy or [])})
        signal_texts = [f"{s.title}. {s.summary or s.body[:300]}" for s in sigs]
        draft = self.llm.draft_insight(cl.label, signal_texts, all_taxonomy)
        evidence = [s.url for s in sigs if s.url] or [s.id for s in sigs]

        insight = Insight(
            id=new_id("ins"),
            cluster_id=cid,
            title=draft["title"],
            what_happened=draft["what_happened"],
            evidence=evidence,
            implications=draft["implications"],
            time_horizon=draft["time_horizon"],
            uncertainties=draft["uncertainties"],
            confidence=draft["confidence"],
            recommended_actions=draft["recommended_actions"],
            exec_summary=draft["exec_summary"],
            analyst_detail=draft["analyst_detail"],
            status="draft",
        )
        self.store.db.upsert_insight(insight)
        await self.emit(Events.INSIGHT_CREATED, {
            "insight_id": insight.id, "cluster_id": cid,
        }, trace_id=event.trace_id)
