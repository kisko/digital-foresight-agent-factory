"""C3 — Trend Trajectory.

Tracks per-cluster time series, assigns a trajectory label, and emits an
inflection event when recent volume slope changes sign.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import urlparse

from shared.contracts import BaseAgent, Event, Events, Signal


WINDOW_DAYS = 7
SLOPE_EPSILON = 0.25


class C3Trajectory(BaseAgent):
    name = "c3.trajectory"
    version = "0.1.0"

    def subscribes(self) -> List[str]:
        return [Events.CLUSTER_UPDATED]

    async def handle(self, event: Event) -> None:
        cluster_id = event.payload["cluster_id"]
        cluster = self.store.db.get_cluster(cluster_id)
        if not cluster:
            return

        now = _parse_dt(event.ts) or datetime.now(timezone.utc)
        signals = [self.store.db.get_signal(sid) for sid in cluster.signal_ids]
        signals = [s for s in signals if s]

        volume = _rolling_volume(signals, now)
        source_diversity = len({s.source for s in signals if s.source})
        geo_spread = len({_source_region(s) for s in signals if _source_region(s)})

        self.store.db.insert_cluster_metric(
            cluster_id=cluster.id,
            ts=now.isoformat(),
            volume=volume,
            source_diversity=source_diversity,
            geo_spread=geo_spread,
        )

        metrics = self.store.db.list_cluster_metrics(cluster.id, limit=4)
        volumes = [int(m["volume"]) for m in metrics]
        previous_trajectory = cluster.trajectory
        cluster.trajectory = _label_trajectory(volumes)
        self.store.db.upsert_cluster(cluster)

        if _is_inflection(volumes):
            await self.emit(
                Events.TRAJECTORY_INFLECTION,
                {
                    "cluster_id": cluster.id,
                    "from": previous_trajectory,
                    "to": cluster.trajectory,
                    "volumes": volumes[-3:],
                },
                trace_id=event.trace_id,
            )


def _rolling_volume(signals: List[Signal], now: datetime) -> int:
    cutoff = now - timedelta(days=WINDOW_DAYS)
    return sum(1 for signal in signals if (_parse_dt(signal.fetched_at) or now) >= cutoff)


def _label_trajectory(volumes: List[int]) -> str:
    if len(volumes) < 2 or volumes[-1] <= 1:
        return "emerging"

    recent = volumes[-3:]
    slope = (recent[-1] - recent[0]) / max(len(recent) - 1, 1)
    if slope > SLOPE_EPSILON:
        return "growing"
    if slope < -SLOPE_EPSILON:
        return "declining"
    return "mature"


def _is_inflection(volumes: List[int]) -> bool:
    if len(volumes) < 3:
        return False
    previous = _sign(volumes[-2] - volumes[-3])
    current = _sign(volumes[-1] - volumes[-2])
    return previous != 0 and current != 0 and previous != current


def _sign(value: int) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _source_region(signal: Signal) -> Optional[str]:
    host = urlparse(signal.url).hostname or signal.source
    parts = [p for p in host.split(".") if p]
    return parts[-1].lower() if parts else None
