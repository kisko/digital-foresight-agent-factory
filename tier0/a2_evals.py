"""A2 — Quality & Evals (thin prototype stub).

Real implementation runs labeled test sets, gates promotion, detects drift.
Prototype just produces a daily-style snapshot the dashboard can show.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from shared.contracts import BaseAgent, Event, Events


class A2Evals(BaseAgent):
    name = "a2.evals"
    version = "0.1.0"

    def subscribes(self) -> List[str]:
        return [Events.INSIGHT_APPROVED, Events.PRODUCT_PUBLISHED]

    async def handle(self, event: Event) -> None:
        # piggyback: every approval triggers a snapshot computation
        snap = self._snapshot()
        await self.emit(Events.EVAL_REPORT_CREATED, snap)

    def _snapshot(self) -> Dict[str, Any]:
        counts = self.store.db.counts()
        insights = self.store.db.list_insights()
        approved = [i for i in insights if i.status == "approved"]
        cited = [i for i in insights if len(i.evidence) >= 3]
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "insights_total": len(insights),
            "insights_approved": len(approved),
            "pct_with_3_citations": round(100.0 * len(cited) / max(len(insights), 1), 1),
            "products_published": counts["products"],
        }
