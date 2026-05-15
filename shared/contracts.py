"""Canonical event types, domain models, and the base Agent contract.

Every agent in the factory — Tier 0, 1, 2, or pod micro-agents — implements
the same contract: subscribe to triggers, read an object reference + context,
write structured output back to the store, emit the next canonical event.
"""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ─── Canonical event topics ────────────────────────────────────────────────
class Events:
    SIGNAL_CREATED      = "signal.created"
    SIGNAL_ENRICHED     = "signal.enriched"
    SIGNAL_SCORED       = "signal.scored"
    CLUSTER_UPDATED     = "cluster.updated"
    INSIGHT_CREATED     = "insight.created"
    INSIGHT_REVIEWED    = "insight.reviewed"
    INSIGHT_APPROVED    = "insight.approved"
    PRODUCT_PUBLISHED   = "product.published"
    AGENT_ERROR         = "agent.error"
    EVAL_REPORT_CREATED = "eval.report.created"
    POLICY_PASS         = "policy.pass"
    POLICY_BLOCK        = "policy.block"

    ALL = [
        SIGNAL_CREATED, SIGNAL_ENRICHED, SIGNAL_SCORED,
        CLUSTER_UPDATED,
        INSIGHT_CREATED, INSIGHT_REVIEWED, INSIGHT_APPROVED,
        PRODUCT_PUBLISHED,
        AGENT_ERROR, EVAL_REPORT_CREATED,
        POLICY_PASS, POLICY_BLOCK,
    ]


# ─── Event envelope ────────────────────────────────────────────────────────
@dataclass
class Event:
    """Every message on the bus uses this envelope."""
    topic: str
    payload: Dict[str, Any]
    agent: str = "system"
    agent_version: str = "0.1.0"
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    trace_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "payload": self.payload,
            "agent": self.agent,
            "agent_version": self.agent_version,
            "ts": self.ts,
            "trace_id": self.trace_id,
        }


# ─── Domain models (kept dict-friendly for SQLite + JSON serialization) ───
@dataclass
class Signal:
    id: str
    title: str
    body: str
    source: str
    url: str
    fetched_at: str
    raw_hash: str
    language: str = "en"
    # enriched fields (populated by B2)
    summary: Optional[str] = None
    entities: List[str] = field(default_factory=list)
    taxonomy: List[str] = field(default_factory=list)
    signal_type: Optional[str] = None
    # scored fields (populated by B3)
    relevance: Optional[float] = None
    novelty: Optional[float] = None
    urgency: Optional[float] = None
    impact: Optional[float] = None
    rationale: Optional[str] = None
    routing: List[str] = field(default_factory=list)
    # clustering (populated by B4)
    cluster_id: Optional[str] = None


@dataclass
class Cluster:
    id: str
    label: str
    descriptor: str
    signal_ids: List[str]
    burst_score: float = 0.0
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Insight:
    id: str
    cluster_id: str
    title: str
    what_happened: str
    evidence: List[str]               # signal IDs / URLs cited
    implications: str
    time_horizon: str                 # near / mid / long
    uncertainties: str
    confidence: str                   # low / medium / high
    recommended_actions: List[str]
    exec_summary: str
    analyst_detail: str
    status: str = "draft"             # draft → reviewed → approved → published
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Product:
    id: str
    kind: str                         # weekly-brief / monthly-deepdive
    title: str
    insight_ids: List[str]
    body_md: str
    path: str
    published_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── Base Agent contract ──────────────────────────────────────────────────
class BaseAgent(abc.ABC):
    """Every agent implements this contract.

    name + version go into every emitted event for traceability. subscribes()
    returns the topics this agent listens to. handle() is called per event.
    """
    name: str = "unnamed"
    version: str = "0.1.0"

    def __init__(self, bus, store, llm):
        self.bus = bus
        self.store = store
        self.llm = llm
        self.log = logging.getLogger(self.name)

    @abc.abstractmethod
    def subscribes(self) -> List[str]:
        ...

    @abc.abstractmethod
    async def handle(self, event: Event) -> None:
        ...

    async def emit(self, topic: str, payload: Dict[str, Any], trace_id: Optional[str] = None) -> None:
        await self.bus.publish(Event(
            topic=topic,
            payload=payload,
            agent=self.name,
            agent_version=self.version,
            trace_id=trace_id,
        ))

    async def start(self) -> None:
        for topic in self.subscribes():
            self.bus.subscribe(topic, self._wrapped_handle)
        self.log.info(f"[{self.name}@{self.version}] subscribed: {self.subscribes()}")

    async def _wrapped_handle(self, event: Event) -> None:
        try:
            await self.handle(event)
        except Exception as e:
            self.log.exception(f"agent error: {e}")
            await self.emit(Events.AGENT_ERROR, {
                "agent": self.name,
                "topic": event.topic,
                "error": str(e),
                "payload": event.payload,
            }, trace_id=event.trace_id)
