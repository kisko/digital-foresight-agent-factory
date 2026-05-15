# Digital Foresight Agent Factory

[![CI](https://github.com/kisko/digital-foresight-agent-factory/actions/workflows/ci.yml/badge.svg)](https://github.com/kisko/digital-foresight-agent-factory/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

A runnable open-source prototype of a multi-agent **digital foresight
factory** — turning a stream of raw signals (research, regulation, releases,
incidents, M&A …) into evidence-backed, decision-relevant insights with full
provenance, human approval gates, and a live dashboard.

This implements **Tier 1 end-to-end** (Ingestion → Normalize → Score →
Cluster → Insight → Publish) plus the Tier 0 control plane (Orchestrator,
Policy, Evals, Knowledge Store) on top of an event-driven backbone — all in
~1500 lines of Python. Every local component has a documented Azure
swap-in point.

> 📐 **Architecture & rationale**: open
> [`docs/architecture-presentation.html`](docs/architecture-presentation.html)
> in a browser for the full design deck (Reveal.js, navigate with arrow keys,
> press `M` for the menu).

## What you get

![pipeline stages](https://img.shields.io/badge/Signal_→_Enriched_→_Scored_→_Clustered_→_Insight_→_Approved_→_Published-38c1ff?style=for-the-badge)

- **10 working agents** wired through an in-process event bus
- **REST API + WebSocket** (FastAPI) with the canonical endpoints from the spec
- **Live dashboard** showing pipeline counts, event stream, and approve buttons
- **Sample data** (18 realistic tech/regulation/security signals) seeded
- **LLM in stub mode** by default — works without any API keys
- **Clean Azure swap-in points** for Service Bus, Cosmos DB, Blob, AI Search,
  Azure OpenAI

## Quick start

```bash
git clone https://github.com/kisko/digital-foresight-agent-factory.git
cd digital-foresight-agent-factory
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m scripts.seed              # seed sample signals
uvicorn api.main:app --reload       # → http://localhost:8000
```

Click **▶ Trigger ingestion** in the dashboard, watch the pipeline flow,
then **Approve** an insight to produce a published Markdown brief.

For a one-shot in-process demo (no API):

```bash
python -m scripts.run_demo
```

See [QUICKSTART.md](QUICKSTART.md) for the full walkthrough.

## Layout

```
.
├── shared/      contracts, event bus, knowledge store, LLM client
├── tier0/       Control Plane (A0 Orchestrator, A1 Policy, A2 Evals, A3 Librarian)
├── tier1/       Production Line (B1 Ingestion → B6 Publish)
├── tier2/       Intelligence Upgrades (C1-C5) — stubs, good first contributions
├── pods/        Tier 3 Domain Pods (Digital/AI reference skeleton)
├── api/         FastAPI: REST + WebSocket
├── dashboard/   Single-page live dashboard
├── data/        sources.yaml, sample signals, runtime DB
├── scripts/     seed + demo runners
├── tests/       pytest smoke test of the end-to-end pipeline
└── docs/        architecture-presentation.html
```

## Mapping to Azure

The prototype runs entirely locally. Each component has a designated Azure
service for the production architecture:

| Prototype | Azure equivalent |
|---|---|
| `shared/eventbus.py` (in-process pub/sub) | **Azure Service Bus** topics |
| `shared/store.py` Blob (filesystem) | **Azure Blob Storage** (WORM) |
| `shared/store.py` Db (SQLite) | **Azure Cosmos DB** |
| `shared/store.py` VectorIndex (numpy) | **Azure AI Search** (vector + hybrid) |
| `shared/llm.py` (stub mode) | **Azure OpenAI** via **AI Foundry** |
| `tier0/a0_orchestrator.py` | **Durable Functions** or Foundry orchestration |
| `api/main.py` (FastAPI) | **Container Apps** behind **API Management** |
| `dashboard/index.html` | **Power BI** or **Static Web Apps** |

Full Azure deployment architecture (landing zone, PTU/PAYG, Purview,
Foundry vs custom mix) is in the
[architecture deck](docs/architecture-presentation.html).

## Contributing

Contributions of all sizes are welcome. Good places to start:

- Implement a **Tier 2 agent** (C1 Evidence, C2 Red Team, C3 Trajectory, C4
  Scenario Hooks, C5 Impact Mapper) — see [`tier2/README.md`](tier2/README.md)
- Wire up **real Azure OpenAI** in `shared/llm.py`
- Add a **live RSS fetcher** to `tier1/b1_ingestion.py`
- Replace toy embeddings in `shared/store.py` `VectorIndex` with real ones

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE). The phrase "The Company" throughout is a generic placeholder
— substitute your own organisation when adapting this prototype.
