# Contributing

Thanks for your interest in contributing! This is an open prototype that
demonstrates a multi-agent digital foresight factory. Contributions of all
sizes are welcome — typo fixes, new agents, Azure plumbing, dashboard
improvements, documentation.

## Quick start

```bash
git clone https://github.com/kisko/digital-foresight-agent-factory.git
cd digital-foresight-agent-factory
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.seed
uvicorn api.main:app --reload
# → open http://localhost:8000
```

See [QUICKSTART.md](QUICKSTART.md) for the full walkthrough.

## How to contribute

1. **Open an issue first** for non-trivial changes — a quick design sanity
   check saves rework. For small fixes, just send a PR.
2. **Fork** the repo and create a feature branch from `main`:
   `git checkout -b feat/c1-evidence-agent`
3. **Make your changes**. Follow the patterns in `tier1/` agents — small,
   single-responsibility, event-driven, idempotent.
4. **Run the tests**: `pytest tests/ -v`. Add tests for new agents.
5. **Submit a PR** against `main`. CI must pass.

## Where to start

Great first contributions:

- **Add a Tier 2 agent** (C1 Evidence, C2 Red Team, C3 Trajectory, C4 Scenario
  Hooks, C5 Impact Mapper). The contracts and trigger events are documented
  in [`tier2/README.md`](tier2/README.md).
- **Add a domain pod** under `pods/` — copy `pods/digital_ai/` and adapt for
  another domain (energy, sustainability, security, …).
- **Wire up real Azure OpenAI** in `shared/llm.py` — the stub mode is fine
  for the prototype, but real LLM calls unlock far better insight quality.
- **Live RSS fetcher** in `tier1/b1_ingestion.py` — currently reads from a
  JSON file. Add an actual RSS/API fetcher driven by `data/sources.yaml`.
- **Real vector embeddings** in `shared/store.py` `VectorIndex` — replace
  the hashed bag-of-words with `text-embedding-3-small` or sentence-transformers.

## Agent contract

Every agent — Tier 0, 1, 2, or pod — implements `BaseAgent` in
`shared/contracts.py`. Specifically:

- `subscribes() -> List[str]`: which canonical event topics trigger this agent
- `handle(event) -> None`: process one event; emit downstream events via `self.emit(...)`
- `name` and `version`: written into every emitted event for traceability

Keep agents **single-responsibility**, **idempotent**, and **bounded** (no
unbounded retries or recursion).

## Code style

- Python 3.9+ compatible
- Type hints on public functions
- Small functions; prefer composition over inheritance
- No comments explaining *what* — only *why* when non-obvious

## Reporting bugs

Use the bug template under `.github/ISSUE_TEMPLATE/`. Please include:

- Steps to reproduce
- Expected vs actual behaviour
- Relevant logs (the API and demo runner log to stderr by default)

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By
participating you agree to abide by its terms.

## License

By contributing you agree that your contributions will be licensed under the
MIT License (see [LICENSE](LICENSE)).
