"""B1 — Ingestion Coordinator.

Prototype mode: there is no live fetcher. Instead, `ingest_from_json(path)`
ingests sample signals from a local file. The contract — emit signal.created
with a stored raw artifact — is identical to what an RSS/API fetcher would do.

To add a real fetcher: drop new methods on this class that emit
signal.created per fetched item; the rest of the pipeline doesn't change.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from shared.contracts import BaseAgent, Event, Events, Signal
from shared.ids import new_id


class B1Ingestion(BaseAgent):
    name = "b1.ingestion"
    version = "0.1.0"

    def subscribes(self) -> List[str]:
        return []  # triggered by scripts, not events

    async def handle(self, event: Event) -> None:
        return  # no-op

    async def ingest_from_json(self, path: Path) -> int:
        """Read a list of {title, body, source, url} from JSON, create signals."""
        items = json.loads(Path(path).read_text())
        n = 0
        for item in items:
            raw = f"{item['title']}\n\n{item['body']}"
            raw_hash, _ = self.store.blob.write_raw(raw)
            sig = Signal(
                id=new_id("sig"),
                title=item["title"],
                body=item["body"],
                source=item.get("source", "unknown"),
                url=item.get("url", ""),
                fetched_at=datetime.now(timezone.utc).isoformat(),
                raw_hash=raw_hash,
                language=item.get("language", "en"),
            )
            self.store.db.upsert_signal(sig)
            await self.emit(Events.SIGNAL_CREATED, {"signal_id": sig.id})
            n += 1
        self.log.info(f"ingested {n} signals from {path}")
        return n
