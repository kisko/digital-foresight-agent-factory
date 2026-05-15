"""B6 — Publishing & Distribution.

Triggers on insight.approved. Generates a Markdown one-pager for each
approved insight and writes it to data/products/. Updates the insight
status to `published` and emits product.published.

In production this is where SharePoint / Teams / Outlook fan-out would go.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from shared.contracts import BaseAgent, Event, Events, Product
from shared.ids import new_id


class B6Publish(BaseAgent):
    name = "b6.publish"
    version = "0.1.0"

    def subscribes(self) -> List[str]:
        return [Events.INSIGHT_APPROVED]

    async def handle(self, event: Event) -> None:
        iid = event.payload["insight_id"]
        i = self.store.db.get_insight(iid)
        if not i or i.status == "published":
            return
        body = self._render_brief(i)
        filename = f"insight-{i.id}.md"
        path = self.store.blob.write_product(filename, body)

        product = Product(
            id=new_id("prd"),
            kind="insight-one-pager",
            title=i.title,
            insight_ids=[iid],
            body_md=body,
            path=str(path),
        )
        self.store.db.upsert_product(product)
        i.status = "published"
        self.store.db.upsert_insight(i)
        await self.emit(Events.PRODUCT_PUBLISHED, {
            "product_id": product.id, "insight_id": iid, "path": str(path),
        }, trace_id=event.trace_id)

    def _render_brief(self, i) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        actions = "\n".join(f"- {a}" for a in i.recommended_actions)
        evidence = "\n".join(f"- {e}" for e in i.evidence)
        return f"""# {i.title}

*Published {now} · Confidence: **{i.confidence}** · Time horizon: **{i.time_horizon}***

## Executive summary
{i.exec_summary}

## What happened
{i.what_happened}

## Implications for The Company
{i.implications}

## Uncertainties
{i.uncertainties}

## Recommended actions
{actions}

## Evidence
{evidence}

---
*Insight ID: `{i.id}` · Cluster: `{i.cluster_id}`*
"""
