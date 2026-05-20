"""Smoke test the end-to-end pipeline.

Runs the same wiring as scripts/run_demo, asserts that signals flow through
to a published product.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone

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
    from tier2.c3_trajectory import C3Trajectory

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
        C3Trajectory(bus, store, llm),
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
    assert any(c.trajectory for c in store.db.list_clusters()), "expected C3 trajectory labels"

    drafts = store.db.list_insights(status="draft")
    assert drafts, "expected draft insights to approve"
    for d in drafts[:2]:
        await a0.approve(d.id, reviewer="test")
    await asyncio.sleep(1.0)

    final = store.db.counts()
    assert final["products"] >= 1, f"expected at least one product published, got {final}"


@pytest.mark.asyncio
async def test_c3_labels_synthetic_burst_as_growing():
    tmp = tempfile.mkdtemp()
    os.environ["FORESIGHT_DATA_DIR"] = tmp
    os.environ["FORESIGHT_DB_PATH"] = str(Path(tmp) / "test.db")

    from shared.contracts import Cluster, Event, Events, Signal
    from shared.eventbus import InProcessEventBus
    from shared.llm import get_llm
    from shared.store import KnowledgeStore
    from tier2.c3_trajectory import C3Trajectory

    bus = InProcessEventBus()
    store = KnowledgeStore(data_dir=Path(tmp))
    llm = get_llm()
    c3 = C3Trajectory(bus, store, llm)

    now = datetime.now(timezone.utc)
    signal_ids = []
    for idx in range(3):
        sid = f"sig_burst_{idx}"
        signal_ids.append(sid)
        store.db.upsert_signal(Signal(
            id=sid,
            title=f"Synthetic burst {idx}",
            body="Synthetic market signal",
            source=f"source{idx}.com",
            url=f"https://source{idx}.com/story",
            fetched_at=(now - timedelta(days=idx)).isoformat(),
            raw_hash=f"hash_{idx}",
            relevance=0.9,
        ))

    cluster = Cluster(
        id="clu_burst",
        label="synthetic burst",
        descriptor="Synthetic burst cluster",
        signal_ids=[],
    )

    for idx, sid in enumerate(signal_ids):
        cluster.signal_ids.append(sid)
        store.db.upsert_cluster(cluster)
        await c3.handle(Event(
            topic=Events.CLUSTER_UPDATED,
            payload={"cluster_id": cluster.id, "signal_id": sid},
            ts=(now + timedelta(minutes=idx)).isoformat(),
        ))
        cluster = store.db.get_cluster(cluster.id)

    assert cluster.trajectory == "growing"
    metrics = store.db.list_cluster_metrics(cluster.id)
    assert [m["volume"] for m in metrics] == [1, 2, 3]


@pytest.mark.asyncio
async def test_c3_emits_inflection_when_slope_flips():
    tmp = tempfile.mkdtemp()
    os.environ["FORESIGHT_DATA_DIR"] = tmp
    os.environ["FORESIGHT_DB_PATH"] = str(Path(tmp) / "test.db")

    from shared.contracts import Cluster, Event, Events, Signal
    from shared.eventbus import InProcessEventBus
    from shared.llm import get_llm
    from shared.store import KnowledgeStore
    from tier2.c3_trajectory import C3Trajectory

    bus = InProcessEventBus()
    store = KnowledgeStore(data_dir=Path(tmp))
    llm = get_llm()
    emitted = []

    async def capture(event):
        emitted.append(event)

    bus.subscribe(Events.TRAJECTORY_INFLECTION, capture)
    c3 = C3Trajectory(bus, store, llm)

    now = datetime.now(timezone.utc)
    for idx in range(4):
        store.db.upsert_signal(Signal(
            id=f"sig_flip_{idx}",
            title=f"Synthetic flip {idx}",
            body="Synthetic market signal",
            source=f"source{idx}.com",
            url=f"https://source{idx}.com/story",
            fetched_at=now.isoformat(),
            raw_hash=f"hash_flip_{idx}",
            relevance=0.9,
        ))

    cluster = Cluster(
        id="clu_flip",
        label="synthetic flip",
        descriptor="Synthetic flip cluster",
        signal_ids=[f"sig_flip_{idx}" for idx in range(4)],
    )
    store.db.upsert_cluster(cluster)
    store.db.insert_cluster_metric(cluster.id, (now - timedelta(minutes=2)).isoformat(), 3, 1, 1)
    store.db.insert_cluster_metric(cluster.id, (now - timedelta(minutes=1)).isoformat(), 1, 1, 1)

    await c3.start()
    await c3.handle(Event(
        topic=Events.CLUSTER_UPDATED,
        payload={"cluster_id": cluster.id, "signal_id": "sig_flip_3"},
        ts=now.isoformat(),
    ))
    await asyncio.sleep(0.1)

    assert emitted, "expected trajectory.inflection event"
    assert emitted[0].payload["cluster_id"] == cluster.id
