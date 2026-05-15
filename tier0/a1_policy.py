"""A1 — Policy & Compliance Gatekeeper.

Prototype scope:
  - On insight.created: verify citations present, attach classification, emit
    policy.pass or policy.block. A draft cannot move to approval without a
    pass.
  - Source allow/deny: read from data/sources.yaml (allow_publish field).

Production swap-in: layer Azure Content Safety + Microsoft Purview on top.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import yaml

from shared.contracts import BaseAgent, Event, Events


SENSITIVE_HINTS = ["confidential", "secret", "internal use only", "do not distribute"]


class A1Policy(BaseAgent):
    name = "a1.policy"
    version = "0.1.0"

    def __init__(self, bus, store, llm, sources_yaml: Path = Path("data/sources.yaml")):
        super().__init__(bus, store, llm)
        self.sources: dict = {}
        if sources_yaml.exists():
            self.sources = yaml.safe_load(sources_yaml.read_text()) or {}

    def subscribes(self) -> List[str]:
        return [Events.INSIGHT_CREATED, Events.INSIGHT_APPROVED]

    async def handle(self, event: Event) -> None:
        if event.topic == Events.INSIGHT_CREATED:
            await self._check_insight(event)
        elif event.topic == Events.INSIGHT_APPROVED:
            # second gate: ensure no sensitive content slipped through
            await self._check_publishability(event)

    async def _check_insight(self, event: Event) -> None:
        iid = event.payload.get("insight_id")
        i = self.store.db.get_insight(iid)
        if not i:
            return
        problems = []
        if len(i.evidence) < 1:
            problems.append("missing citations")
        text = f"{i.what_happened}\n{i.implications}\n{i.exec_summary}".lower()
        for hint in SENSITIVE_HINTS:
            if hint in text:
                problems.append(f"sensitive marker: '{hint}'")
        if problems:
            await self.emit(Events.POLICY_BLOCK, {
                "insight_id": iid,
                "reason": "; ".join(problems),
                "remediation": "Add citations and/or remove sensitive markers before approval.",
            })
        else:
            await self.emit(Events.POLICY_PASS, {
                "insight_id": iid,
                "classification": "internal",
            })

    async def _check_publishability(self, event: Event) -> None:
        iid = event.payload.get("insight_id")
        i = self.store.db.get_insight(iid)
        if not i:
            return
        # check each evidence source URL is allowed
        denied = []
        allow = (self.sources.get("allow_domains") or [])
        if allow:
            for ev_url in i.evidence:
                if ev_url.startswith("http") and not any(d in ev_url for d in allow):
                    denied.append(ev_url)
        if denied:
            await self.emit(Events.POLICY_BLOCK, {
                "insight_id": iid,
                "reason": f"sources not on allow-list: {denied[:3]}",
                "remediation": "Use only allow-listed sources or request an exception.",
            })
        else:
            await self.emit(Events.POLICY_PASS, {
                "insight_id": iid,
                "stage": "pre-publish",
            })
