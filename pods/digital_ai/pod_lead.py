"""Digital/AI Pod Lead — synthesizer skeleton.

Subscribes to insight.approved with taxonomy ∈ {ai/*}. On a weekly tick,
groups approved insights into a domain weekly synthesis.

This is a deliberately thin sample — extend with micro-agents per the deck:
  - regulation_watch
  - market_ecosystem
  - academic_frontier
  - patents_ip
  - incidents_ops
  - adoption_maturity
  - customer_qa
  - foundation_model_watch
  - data_architecture_patterns
"""
from __future__ import annotations

from typing import List

from shared.contracts import BaseAgent, Event, Events


class DigitalAIPodLead(BaseAgent):
    name = "pod.digital_ai.lead"
    version = "0.1.0"
    pod_taxonomy_prefix = "ai/"

    def subscribes(self) -> List[str]:
        return [Events.INSIGHT_APPROVED]

    async def handle(self, event: Event) -> None:
        iid = event.payload["insight_id"]
        ins = self.store.db.get_insight(iid)
        if not ins:
            return
        cl = self.store.db.get_cluster(ins.cluster_id)
        if not cl:
            return
        sigs = [self.store.db.get_signal(s) for s in cl.signal_ids]
        in_pod = any(any(t.startswith(self.pod_taxonomy_prefix) for t in (s.taxonomy or []))
                     for s in sigs if s)
        if not in_pod:
            return
        self.log.info(f"[digital_ai pod] adopting insight {iid} into pod synthesis queue")
