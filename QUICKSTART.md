# Quickstart

## 1. Install

```bash
cd /Users/kis/foresight-factory
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Seed sample data

```bash
python -m scripts.seed
```

This creates `data/foresight.db`, drops 18 realistic sample signals into the
`signals` table, and emits a `signal.created` event for each. Subscribing
agents are not running yet, so they sit in the queue.

## 3. Start the API + dashboard

```bash
uvicorn api.main:app --reload --port 8000
```

Open **http://localhost:8000**. You should see:

- **Pipeline stages** (Signal → Enriched → Scored → Clustered → Insight → Approved → Published) with live counts
- **Live event stream** on the right
- **Pending insights** with **Approve** buttons

When the API boots it starts all Tier 0 + Tier 1 agents. They subscribe to the
event bus, drain the seeded `signal.created` queue, and you'll see signals
move through the pipeline in real time.

## 4. Run a one-shot pipeline demo (no API)

```bash
python -m scripts.run_demo
```

Runs the full pipeline in-process to console. Useful for debugging individual
agents or running in CI.

## 5. Approve an insight → produce a brief

In the dashboard, click **Approve** on any insight. B6 (publishing) picks it
up, generates a Markdown brief at `data/products/weekly-brief-*.md`, and the
**Published** count ticks up.

## 6. Where to extend

- **Add an agent**: copy `tier1/b2_normalize.py`, register in
  `api/main.py:start_agents()`. The contract is `BaseAgent` in
  `shared/contracts.py`.
- **Plug in Azure OpenAI**: set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`,
  `AZURE_OPENAI_DEPLOYMENT` in `.env`. `shared/llm.py` auto-switches from
  stub mode.
- **Plug in real Service Bus**: swap `shared/eventbus.py` `InProcessEventBus`
  for a `ServiceBusEventBus` with the same interface.
- **Add a Tier 2 upgrade**: add file in `tier2/`, subscribe to
  `insight.created`, emit findings on `insight.enriched`.

## VSCode

Open `foresight-factory.code-workspace`. The debug panel has three
configurations: **API (uvicorn)**, **Seed**, **Demo run**. Set breakpoints
inside any agent and step through events as they fire.
