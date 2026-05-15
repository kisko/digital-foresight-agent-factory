"""Seed the local store with sample signals.

Run as: `python -m scripts.seed`
This only writes signals to the DB — it does NOT run the pipeline. Start the
API (`uvicorn api.main:app --reload`) and click "Trigger ingestion" in the
dashboard, OR run `python -m scripts.run_demo` to see the pipeline in action.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from shared.eventbus import get_bus
from shared.llm import get_llm
from shared.store import KnowledgeStore
from tier1.b1_ingestion import B1Ingestion


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    store = KnowledgeStore()
    bus = get_bus()
    llm = get_llm()
    b1 = B1Ingestion(bus, store, llm)
    await b1.start()
    n = await b1.ingest_from_json(Path("data/sample_signals.json"))
    print(f"\n✓ seeded {n} signals into {store.db.path}")
    print("  · counts:", store.db.counts())
    print("\nNext: `uvicorn api.main:app --reload` and open http://localhost:8000")


if __name__ == "__main__":
    asyncio.run(main())
