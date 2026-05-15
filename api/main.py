"""FastAPI front door — REST endpoints + WebSocket for live dashboard.

On startup, instantiates the shared store/bus/llm, wires up all Tier 0 + 1
agents (+ the Digital/AI pod lead), and starts them subscribing to the bus.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from shared.contracts import Event, Events
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

from pods.digital_ai.pod_lead import DigitalAIPodLead


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("api")

DASHBOARD_HTML = Path(__file__).parent.parent / "dashboard" / "index.html"
ARCHITECTURE_HTML = Path(__file__).parent.parent / "docs" / "architecture-presentation.html"

# ─── module-level singletons (lifespan-managed) ────────────────────────────
store: Optional[KnowledgeStore] = None
bus = None
llm = None
agents: dict = {}
ws_clients: Set[WebSocket] = set()
ws_queue: asyncio.Queue = asyncio.Queue()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store, bus, llm, agents
    store = KnowledgeStore()
    bus = get_bus()
    llm = get_llm()

    agents["a0"] = A0Orchestrator(bus, store, llm)
    agents["a1"] = A1Policy(bus, store, llm)
    agents["a2"] = A2Evals(bus, store, llm)
    agents["a3"] = A3Librarian(bus, store, llm)
    agents["b1"] = B1Ingestion(bus, store, llm)
    agents["b2"] = B2Normalize(bus, store, llm)
    agents["b3"] = B3Relevance(bus, store, llm)
    agents["b4"] = B4Cluster(bus, store, llm)
    agents["b5"] = B5Insight(bus, store, llm)
    agents["b6"] = B6Publish(bus, store, llm)
    agents["pod.digital_ai"] = DigitalAIPodLead(bus, store, llm)

    for a in agents.values():
        await a.start()

    # tap the bus and forward every event to connected WebSockets
    def _on_event(ev: Event):
        try:
            ws_queue.put_nowait(ev.to_dict())
        except asyncio.QueueFull:
            pass

    bus.tap(_on_event)
    pump_task = asyncio.create_task(_ws_pump())
    log.info(f"foresight factory online · LLM mode: {llm.mode}")
    try:
        yield
    finally:
        pump_task.cancel()


app = FastAPI(title="Foresight Agent Factory", lifespan=lifespan)


async def _ws_pump():
    """Drain ws_queue → broadcast to all connected clients."""
    while True:
        evt = await ws_queue.get()
        dead = []
        for ws in list(ws_clients):
            try:
                await ws.send_json({"type": "event", "data": evt})
            except Exception:
                dead.append(ws)
        for d in dead:
            ws_clients.discard(d)


# ─── Dashboard ─────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return FileResponse(DASHBOARD_HTML)


@app.get("/architecture")
def architecture():
    return FileResponse(ARCHITECTURE_HTML)


# ─── Signals ───────────────────────────────────────────────────────────────
@app.get("/signals")
def list_signals(min_relevance: float = 0.0, theme: Optional[str] = None, limit: int = 100):
    sigs = store.db.list_signals(limit=limit)
    if min_relevance:
        sigs = [s for s in sigs if (s.relevance or 0) >= min_relevance]
    if theme:
        sigs = [s for s in sigs if theme in (s.taxonomy or [])]
    return [asdict(s) for s in sigs]


@app.get("/signals/{sid}")
def get_signal(sid: str):
    s = store.db.get_signal(sid)
    if not s:
        raise HTTPException(404, "signal not found")
    return asdict(s)


# ─── Clusters ──────────────────────────────────────────────────────────────
@app.get("/clusters")
def list_clusters():
    return [asdict(c) for c in store.db.list_clusters()]


@app.get("/clusters/{cid}")
def get_cluster(cid: str):
    c = store.db.get_cluster(cid)
    if not c:
        raise HTTPException(404, "cluster not found")
    return asdict(c)


# ─── Insights ──────────────────────────────────────────────────────────────
@app.get("/insights")
def list_insights(status: Optional[str] = None):
    return [asdict(i) for i in store.db.list_insights(status=status)]


@app.get("/insights/{iid}")
def get_insight(iid: str):
    i = store.db.get_insight(iid)
    if not i:
        raise HTTPException(404, "insight not found")
    return asdict(i)


@app.post("/insights/{iid}/approve")
async def approve_insight(iid: str, reviewer: str = "human"):
    try:
        approved = await agents["a0"].approve(iid, reviewer=reviewer)
        return asdict(approved)
    except KeyError as e:
        raise HTTPException(404, str(e))


# ─── Products ──────────────────────────────────────────────────────────────
@app.get("/products")
def list_products():
    return [asdict(p) for p in store.db.list_products()]


@app.get("/products/{pid}/raw", response_class=PlainTextResponse)
def get_product_raw(pid: str):
    for p in store.db.list_products():
        if p.id == pid:
            return p.body_md
    raise HTTPException(404, "product not found")


# ─── Orchestrator / dashboard surface ─────────────────────────────────────
@app.get("/pipeline")
def pipeline():
    counts = agents["a0"].pipeline_counts()
    return {
        "stages": counts,
        "audit_tail": agents["a0"].audit_tail(20),
        "llm_mode": llm.mode,
    }


@app.get("/agents")
def list_agents():
    return [{"name": a.name, "version": a.version, "subscribes": a.subscribes()}
            for a in agents.values()]


@app.get("/events")
def event_history(limit: int = 50):
    return [ev.to_dict() for ev in bus.history(limit=limit)]


# ─── Ingestion trigger (for the seeded JSON) ──────────────────────────────
@app.post("/ingest")
async def ingest(path: str = "data/sample_signals.json"):
    n = await agents["b1"].ingest_from_json(Path(path))
    return {"ingested": n}


# ─── WebSocket — live event stream ────────────────────────────────────────
@app.websocket("/ws")
async def ws_events(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    # send a hello so the dashboard knows it's connected
    await ws.send_json({"type": "hello", "data": {"llm_mode": llm.mode}})
    try:
        while True:
            # keep-alive — the dashboard doesn't send anything
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(ws)
