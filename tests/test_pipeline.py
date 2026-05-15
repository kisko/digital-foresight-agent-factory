"""Smoke test the end-to-end pipeline.

Runs the same wiring as scripts/run_demo, asserts that signals flow through
to a published product.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_pipeline_end_to_end():
    # isolate from any seeded local DB
    tmp = tempfile.mkdtemp()
    os.environ["FORESIGHT_DATA_DIR"] = tmp
    os.environ["FORESIGHT_DB_PATH"] = str(Path(tmp) / "test.db")

    # re-import after env set so KnowledgeStore picks it up
    from shared.eventbus import InProcessEventBus
    from shared.llm import get_llm
    from shared.store import KnowledgeStore

    from tier0.a0_orchestrator import A0Orchestrator
    from tier0.a1_policy import A1Policy
    from tier0.a3_librarian import A3Librarian

    from tier1.b1_ingestion import B1Ingestion
    from tier1.b2_normalize import B2Normalize
    from tier1.b3_relevance import B3Relevance
    from tier1.b4_cluster import B4Cluster
    from tier1.b5_insight import B5Insight
    from tier1.b6_publish import B6Publish

    bus = InProcessEventBus()
    store = KnowledgeStore(data_dir=Path(tmp))
    llm = get_llm()

    a0 = A0Orchestrator(bus, store, llm)
    agents = [
        a0,
        A1Policy(bus, store, llm),
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
    await b1.ingest_from_json(Path("data/sample_signals.json"))
    await asyncio.sleep(2.0)

    counts = store.db.counts()
    assert counts["signals"] >= 15, f"expected signals to be ingested, got {counts}"
    assert counts["clusters"] >= 1, "expected at least one cluster"
    assert counts["insights"] >= 1, "expected at least one draft insight"

    drafts = store.db.list_insights(status="draft")
    assert drafts, "expected draft insights to approve"
    for d in drafts[:2]:
        await a0.approve(d.id, reviewer="test")
    await asyncio.sleep(1.0)

    final = store.db.counts()
    assert final["products"] >= 1, f"expected at least one product published, got {final}"
