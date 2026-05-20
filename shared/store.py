"""Knowledge Store — A3 Librarian's backend.

Three things stitched together:
  - Blob   : immutable raw artifacts on disk          → Azure Blob Storage (WORM)
  - Db     : SQLite for signals/clusters/insights     → Azure Cosmos DB
  - Vector : numpy-free cosine via token-bag hashing  → Azure AI Search

For the prototype, embeddings are a deterministic hashed bag-of-words. They
work well enough for clustering of distinct topics. Swap for real embeddings
(`text-embedding-3-small`) when wiring up Azure OpenAI.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from shared.contracts import Cluster, Insight, Product, Signal


# ─── Blob ──────────────────────────────────────────────────────────────────
class Blob:
    """Immutable, hash-named file storage. Stand-in for Blob Storage (WORM)."""
    def __init__(self, root: Path):
        self.root = root
        (self.root / "raw").mkdir(parents=True, exist_ok=True)
        (self.root / "products").mkdir(parents=True, exist_ok=True)

    def write_raw(self, content: str) -> Tuple[str, Path]:
        h = hashlib.sha256(content.encode("utf-8")).hexdigest()
        path = self.root / "raw" / f"{h}.txt"
        if not path.exists():
            path.write_text(content, encoding="utf-8")
        return h, path

    def read_raw(self, h: str) -> Optional[str]:
        path = self.root / "raw" / f"{h}.txt"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def write_product(self, filename: str, body: str) -> Path:
        path = self.root / "products" / filename
        path.write_text(body, encoding="utf-8")
        return path


# ─── Vector index (toy cosine for clustering) ─────────────────────────────
_TOKEN_RE = re.compile(r"[A-Za-z0-9]{3,}")
_VEC_DIM = 256


def _embed(text: str) -> List[float]:
    """Deterministic hashed bag-of-tokens. ~Random projection. Good enough
    for the prototype's clustering demo. Replace with a real embedding model."""
    vec = [0.0] * _VEC_DIM
    for tok in _TOKEN_RE.findall(text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % _VEC_DIM] += 1.0
    # L2 normalize
    n = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / n for x in vec]


def _cosine(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class VectorIndex:
    """In-memory vector store. Rebuilt from DB on startup."""
    def __init__(self):
        self._items: Dict[str, List[float]] = {}

    def add(self, key: str, text: str) -> None:
        self._items[key] = _embed(text)

    def search(self, query_text: str, k: int = 5) -> List[Tuple[str, float]]:
        q = _embed(query_text)
        scored = [(key, _cosine(q, v)) for key, v in self._items.items()]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def pairs(self) -> List[Tuple[str, List[float]]]:
        return list(self._items.items())


# ─── Db (SQLite) ───────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
  id TEXT PRIMARY KEY,
  data JSON NOT NULL,
  raw_hash TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS clusters (
  id TEXT PRIMARY KEY,
  data JSON NOT NULL,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS cluster_metrics (
  cluster_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  volume INTEGER NOT NULL,
  source_diversity INTEGER NOT NULL,
  geo_spread INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cluster_metrics_cluster_ts
  ON cluster_metrics(cluster_id, ts);
CREATE TABLE IF NOT EXISTS insights (
  id TEXT PRIMARY KEY,
  data JSON NOT NULL,
  status TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS products (
  id TEXT PRIMARY KEY,
  data JSON NOT NULL,
  published_at TEXT
);
"""


class Db:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    # ── signals
    def upsert_signal(self, s: Signal) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO signals (id, data, raw_hash, created_at) VALUES (?,?,?,?)",
                (s.id, json.dumps(asdict(s)), s.raw_hash, s.fetched_at),
            )

    def get_signal(self, sid: str) -> Optional[Signal]:
        with self._conn() as c:
            row = c.execute("SELECT data FROM signals WHERE id=?", (sid,)).fetchone()
            return Signal(**json.loads(row["data"])) if row else None

    def list_signals(self, limit: int = 200) -> List[Signal]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT data FROM signals ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [Signal(**json.loads(r["data"])) for r in rows]

    def signals_in_window(self, only_scored: bool = True) -> List[Signal]:
        sigs = self.list_signals(limit=500)
        return [s for s in sigs if (s.relevance is not None) or not only_scored]

    # ── clusters
    def upsert_cluster(self, cl: Cluster) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO clusters (id, data, updated_at) VALUES (?,?,?)",
                (cl.id, json.dumps(asdict(cl)), cl.updated_at),
            )

    def get_cluster(self, cid: str) -> Optional[Cluster]:
        with self._conn() as c:
            row = c.execute("SELECT data FROM clusters WHERE id=?", (cid,)).fetchone()
            return Cluster(**json.loads(row["data"])) if row else None

    def list_clusters(self) -> List[Cluster]:
        with self._conn() as c:
            rows = c.execute("SELECT data FROM clusters ORDER BY updated_at DESC").fetchall()
            return [Cluster(**json.loads(r["data"])) for r in rows]

    # ── cluster metrics
    def insert_cluster_metric(
        self,
        cluster_id: str,
        ts: str,
        volume: int,
        source_diversity: int,
        geo_spread: int,
    ) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO cluster_metrics (cluster_id, ts, volume, source_diversity, geo_spread) VALUES (?,?,?,?,?)",
                (cluster_id, ts, volume, source_diversity, geo_spread),
            )

    def list_cluster_metrics(self, cluster_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT cluster_id, ts, volume, source_diversity, geo_spread
                FROM cluster_metrics
                WHERE cluster_id=?
                ORDER BY ts DESC
                LIMIT ?
                """,
                (cluster_id, limit),
            ).fetchall()
            metrics = [dict(r) for r in rows]
            metrics.reverse()
            return metrics

    # ── insights
    def upsert_insight(self, i: Insight) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO insights (id, data, status, created_at) VALUES (?,?,?,?)",
                (i.id, json.dumps(asdict(i)), i.status, i.created_at),
            )

    def get_insight(self, iid: str) -> Optional[Insight]:
        with self._conn() as c:
            row = c.execute("SELECT data FROM insights WHERE id=?", (iid,)).fetchone()
            return Insight(**json.loads(row["data"])) if row else None

    def list_insights(self, status: Optional[str] = None) -> List[Insight]:
        q = "SELECT data FROM insights"
        params: Tuple[Any, ...] = ()
        if status:
            q += " WHERE status=?"
            params = (status,)
        q += " ORDER BY created_at DESC"
        with self._conn() as c:
            rows = c.execute(q, params).fetchall()
            return [Insight(**json.loads(r["data"])) for r in rows]

    # ── products
    def upsert_product(self, p: Product) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO products (id, data, published_at) VALUES (?,?,?)",
                (p.id, json.dumps(asdict(p)), p.published_at),
            )

    def list_products(self) -> List[Product]:
        with self._conn() as c:
            rows = c.execute("SELECT data FROM products ORDER BY published_at DESC").fetchall()
            return [Product(**json.loads(r["data"])) for r in rows]

    def counts(self) -> Dict[str, int]:
        with self._conn() as c:
            return {
                "signals":  c.execute("SELECT COUNT(*) FROM signals").fetchone()[0],
                "clusters": c.execute("SELECT COUNT(*) FROM clusters").fetchone()[0],
                "insights": c.execute("SELECT COUNT(*) FROM insights").fetchone()[0],
                "products": c.execute("SELECT COUNT(*) FROM products").fetchone()[0],
                "insights_pending":  c.execute("SELECT COUNT(*) FROM insights WHERE status='draft'").fetchone()[0],
                "insights_approved": c.execute("SELECT COUNT(*) FROM insights WHERE status='approved'").fetchone()[0],
            }


# ─── Knowledge Store facade (A3 librarian backend) ────────────────────────
class KnowledgeStore:
    def __init__(self, data_dir: Optional[Path] = None):
        data_dir = data_dir or Path(os.getenv("FORESIGHT_DATA_DIR", "./data"))
        self.blob = Blob(data_dir)
        self.db = Db(Path(os.getenv("FORESIGHT_DB_PATH", str(data_dir / "foresight.db"))))
        self.vec = VectorIndex()
        self._rebuild_vectors()

    def _rebuild_vectors(self) -> None:
        for s in self.db.list_signals(limit=1000):
            text = f"{s.title}\n{s.summary or s.body[:500]}"
            self.vec.add(s.id, text)

    # convenience for B5 (insight drafting): top-k similar for a cluster
    def retrieval_pack(self, cluster_id: str, k: int = 5) -> List[Signal]:
        cl = self.db.get_cluster(cluster_id)
        if not cl:
            return []
        return [s for s in (self.db.get_signal(sid) for sid in cl.signal_ids) if s][:k]
