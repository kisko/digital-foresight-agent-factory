"""Run the full pipeline end-to-end, in-process, with verbose logging.

`python -m scripts.run_demo`

Wires the same agents as the API does, then triggers ingestion and waits a
few seconds for the event chain to settle. Approves all draft insights at
the end so B6 produces published briefs.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from shared.eventbus import get_bus
from shared.llm import get_llm
from shared.store import KnowledgeStore

from tier0.a0_orchestrator import A0Orchestrator
from tier0.a1_policy import A1Policy
from tier0.a2_evals import A2Evals
from tier0.a3_librarian import A3Librarian

from tier1.b1_ingestion import B1Ingestion
from tier1.b2_normalize import B2Normalize
from tier1.b3_relevance import B3Relevance
from tier1.b4_cluster import B4Cluster
from tier1.b5_insight import B5Insight
from tier1.b6_publish import B6Publish


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d [%(name)-18s] %(message)s",
        datefmt="%H:%M:%S",
    )
    bus, store, llm = get_bus(), KnowledgeStore(), get_llm()
    log = logging.getLogger("demo")
    log.info(f"LLM mode: {llm.mode}")

    a0 = A0Orchestrator(bus, store, llm)
    agents = [
        a0,
        A1Policy(bus, store, llm),
        A2Evals(bus, store, llm),
        A3Librarian(bus, store, llm),
        B1Ingestion(bus, store, llm),
        B2Normalize(bus, store, llm),
        B3Relevance(bus, store, llm),
        B4Cluster(bus, store, llm),
        B5Insight(bus, store, llm),
        B6Publish(bus, store, llm),
    ]
    for a in agents:
        await a.start()

    b1 = next(a for a in agents if a.name == "b1.ingestion")
    log.info("─── ingest ───")
    await b1.ingest_from_json(Path("data/sample_signals.json"))

    # Let the chain settle. Generous to ensure cluster/insight events fire.
    log.info("─── settling pipeline ───")
    await asyncio.sleep(2.0)

    log.info("─── pipeline counts ───")
    log.info(a0.pipeline_counts())

    drafts = store.db.list_insights(status="draft")
    log.info(f"─── approving {len(drafts)} draft insights ───")
    for d in drafts:
        await a0.approve(d.id, reviewer="demo-runner")
    await asyncio.sleep(1.5)

    log.info("─── final counts ───")
    log.info(store.db.counts())
    log.info(f"products at: {[p.path for p in store.db.list_products()][:3]}")
    log.info("✓ done")


if __name__ == "__main__":
    asyncio.run(main())
