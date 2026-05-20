# Tier 2 — Intelligence Upgrades

C3 is implemented in the prototype; the other upgrades remain ready for
focused contributions once the MVP pipeline is stable.

| Agent | Trigger | What it adds |
|---|---|---|
| C1 Evidence & Credibility | `insight.created` | Triangulates claims, scores credibility, flags hype |
| C2 Contrarian / Red Team | `insight.created` | Counterarguments, falsification tests, caveats |
| C3 Trend Trajectory | `cluster.updated` | Per-cluster time series, inflection points, stage label |
| C4 Scenario Hooks | `cluster.updated` | Maps to assumptions; fires alerts when assumptions shift |
| C5 Impact & Dependency Mapper | `insight.approved` | Value-chain map, dependencies, structured risk/opp entries |

Each follows the same `BaseAgent` contract. The orchestrator (A0) invokes
them only when relevance/impact warrants it — they shouldn't fire on every
insight, just the ones that move the needle.
