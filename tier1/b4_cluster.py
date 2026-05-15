"""B4 — Deduplication & Clustering.

Strategy for the prototype: cluster primarily by **primary taxonomy** (the
B2 enrichment), with vector similarity as a tiebreaker for finer separation
within a taxonomy. This makes clustering deterministic and visible in the
demo without depending on the quality of the bag-of-words embedding.

Production swap-in: replace `_pick_cluster` with an AI Search hybrid query
(vector + taxonomy filter) + a real embedding model.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import List, Optional

from shared.contracts import BaseAgent, Cluster, Event, Events, Signal
from shared.ids import new_id

SIMILARITY_FALLBACK = 0.25
RELEVANCE_FLOOR = 0.10


class B4Cluster(BaseAgent):
    name = "b4.cluster"
    version = "0.2.0"

    def subscribes(self) -> List[str]:
        return [Events.SIGNAL_SCORED]

    async def handle(self, event: Event) -> None:
        sid = event.payload["signal_id"]
        sig = self.store.db.get_signal(sid)
        if not sig or (sig.relevance or 0) < RELEVANCE_FLOOR:
            return
        target_cluster = self._pick_cluster(sig)
        if target_cluster is None:
            target_cluster = self._new_cluster(sig)
        else:
            self._join_cluster(target_cluster, sig)
        sig.cluster_id = target_cluster
        self.store.db.upsert_signal(sig)
        await self.emit(Events.CLUSTER_UPDATED, {
            "cluster_id": target_cluster,
            "signal_id": sid,
        }, trace_id=event.trace_id)

    # ── cluster selection
    def _pick_cluster(self, sig: Signal) -> Optional[str]:
        if not sig.taxonomy:
            return None
        primary_tax = sig.taxonomy[0]
        # Match by cluster *dominant* taxonomy. This keeps storylines tight:
        # foundation-models stays separate from incidents, regulation, etc.
        for cl in self.store.db.list_clusters():
            members = [self.store.db.get_signal(s) for s in cl.signal_ids]
            members = [m for m in members if m]
            if not members:
                continue
            tax_counts = Counter(t for m in members for t in (m.taxonomy or []))
            if not tax_counts:
                continue
            dominant = tax_counts.most_common(1)[0][0]
            if dominant == primary_tax:
                return cl.id
        # fallback: vector similarity (handles taxonomy=uncategorized cases)
        text = f"{sig.title}\n{sig.summary or sig.body[:300]}"
        for cand_id, score in self.store.vec.search(text, k=5):
            if cand_id == sig.id or score < SIMILARITY_FALLBACK:
                continue
            cand = self.store.db.get_signal(cand_id)
            if cand and cand.cluster_id:
                return cand.cluster_id
        return None

    # ── cluster mutations
    def _new_cluster(self, sig: Signal) -> str:
        cid = new_id("clu")
        primary_tax = sig.taxonomy[0] if sig.taxonomy else "general"
        cl = Cluster(
            id=cid,
            label=f"{primary_tax} storyline",
            descriptor=sig.summary or sig.title,
            signal_ids=[sig.id],
            burst_score=0.1,
        )
        self.store.db.upsert_cluster(cl)
        return cid

    def _join_cluster(self, cid: str, sig: Signal) -> None:
        cl = self.store.db.get_cluster(cid)
        if not cl or sig.id in cl.signal_ids:
            return
        cl.signal_ids.append(sig.id)
        cl.updated_at = datetime.now(timezone.utc).isoformat()
        cl.label = self._label_from_cluster(cl)
        cl.burst_score = round(min(len(cl.signal_ids) / 4.0, 1.0), 2)
        self.store.db.upsert_cluster(cl)

    def _label_from_cluster(self, cl: Cluster) -> str:
        sigs = [self.store.db.get_signal(s) for s in cl.signal_ids]
        sigs = [s for s in sigs if s]
        tax_counts = Counter(t for s in sigs for t in (s.taxonomy or []))
        top_tax = tax_counts.most_common(1)[0][0] if tax_counts else "general"
        return f"{top_tax} — {len(sigs)} signals"
