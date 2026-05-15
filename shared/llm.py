"""LLM client with Azure OpenAI swap-in.

If AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_KEY + AZURE_OPENAI_DEPLOYMENT are set,
calls are made against Azure OpenAI. Otherwise we run in deterministic stub
mode so the prototype is fully demoable without keys.

The stub functions are intentionally crude — they're not pretending to be
smart. They give each agent realistic-shaped output so the pipeline visibly
works. Replace with real LLM prompts when wiring up production.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from typing import Dict, List, Optional


STOP = set("""a an and are as at be by for from has have if in into is it of on
or that the this to was were will with you your we our its their they them
about over under between against during without within across""".split())

TAXONOMY_HINTS: Dict[str, List[str]] = {
    "ai/foundation-models": ["gpt", "claude", "llama", "foundation model", "frontier model", "llm"],
    "ai/agents":            ["agent", "agentic", "tool use", "autogen", "langchain", "orchestrat"],
    "ai/governance":        ["eu ai act", "ai act", "nist", "iso 42001", "governance", "compliance"],
    "data/architecture":    ["data mesh", "lakehouse", "fabric", "iceberg", "delta lake", "mlops"],
    "security/incident":    ["breach", "vulnerability", "cve", "ransomware", "exploit", "leak"],
    "regulation":           ["regulation", "directive", "compliance", "law", "court", "ruling"],
    "research/paper":       ["arxiv", "paper", "preprint", "study", "benchmark"],
    "funding/m&a":          ["raises", "funding", "series ", "acquired", "acquisition", "ipo"],
    "release":              ["released", "launches", "announces", "ga ", "general availability"],
    "patent":               ["patent", "uspto", "epo"],
}

SIGNAL_TYPES: Dict[str, List[str]] = {
    "regulation": ["regulation", "directive", "act", "law", "ruling"],
    "research":   ["paper", "arxiv", "study", "benchmark"],
    "incident":   ["breach", "outage", "vulnerability", "exploit"],
    "funding":    ["raises", "funding", "series ", "acquired"],
    "release":    ["released", "launches", "announces", "ga "],
    "patent":     ["patent"],
}


def _llm_enabled() -> bool:
    return all([
        os.getenv("AZURE_OPENAI_ENDPOINT"),
        os.getenv("AZURE_OPENAI_KEY"),
        os.getenv("AZURE_OPENAI_DEPLOYMENT"),
    ])


# ─── Public surface used by agents ─────────────────────────────────────────
class LLM:
    """Single facade. Each method has a stub + an Azure swap-in placeholder."""

    def __init__(self):
        self.mode = "azure" if _llm_enabled() else "stub"

    # B2 ──────────────────────────────────────────────────────────────────
    def summarize(self, text: str, max_chars: int = 280) -> str:
        text = text.strip().replace("\n", " ")
        if self.mode == "azure":
            return self._azure_chat(
                "You write 2-sentence neutral summaries. No hype.",
                f"Summarize:\n{text}",
                max_tokens=120,
            ) or text[:max_chars]
        # stub: first 2 sentences or first 280 chars
        sents = re.split(r"(?<=[.!?])\s+", text)
        s = " ".join(sents[:2])
        return s[:max_chars]

    def extract_entities(self, text: str) -> List[str]:
        # crude but reliable: Capitalised multi-word phrases + common tech acronyms
        ents = set(re.findall(r"\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)+)\b", text))
        for tok in re.findall(r"\b([A-Z]{2,6})\b", text):
            ents.add(tok)
        return sorted(ents)[:10]

    def classify_taxonomy(self, text: str) -> List[str]:
        t = text.lower()
        labels = [label for label, hints in TAXONOMY_HINTS.items() if any(h in t for h in hints)]
        return labels[:3] or ["uncategorized"]

    def classify_signal_type(self, text: str) -> str:
        t = text.lower()
        for stype, hints in SIGNAL_TYPES.items():
            if any(h in t for h in hints):
                return stype
        return "general"

    # B3 ──────────────────────────────────────────────────────────────────
    def score_signal(self, signal_text: str, lens_keywords: List[str]) -> Dict[str, float]:
        t = signal_text.lower()
        kw_hits = sum(1 for k in lens_keywords if k.lower() in t)
        # any keyword hit → already relevant; saturate at ~3 hits
        kw_ratio = min(kw_hits / 3.0, 1.0)
        words = re.findall(r"[a-z]{4,}", t)
        novelty = min(len(set(words)) / 60, 1.0)
        urgency_kw = ["urgent", "immediate", "breach", "incident", "exploit",
                      "released today", "ga ", "general availability",
                      "deadline", "enforcement", "vulnerability", "flash crash"]
        urgency = min(sum(1 for k in urgency_kw if k in t) * 0.5, 1.0)
        impact = round(kw_ratio * 0.7 + novelty * 0.3, 2)
        relevance = round(min(kw_ratio * 0.7 + urgency * 0.2 + novelty * 0.1, 1.0), 2)
        return {
            "relevance": relevance,
            "novelty":   round(novelty, 2),
            "urgency":   round(urgency, 2),
            "impact":    impact,
        }

    def rationale(self, signal_title: str, taxonomy: List[str]) -> str:
        # 2-3 bullets, deterministic
        bits = []
        if taxonomy:
            bits.append(f"Falls under {', '.join(taxonomy)} — directly in The Company's foresight scope.")
        bits.append(f"Headline '{signal_title}' suggests near-term decision relevance.")
        bits.append("Worth tracking the cluster trajectory over the next 2-4 weeks.")
        return "\n".join(f"- {b}" for b in bits)

    # B5 ──────────────────────────────────────────────────────────────────
    def draft_insight(self, cluster_label: str, signal_texts: List[str], taxonomy: List[str]) -> Dict[str, str]:
        joined = " ".join(signal_texts).lower()
        top_terms = [w for w, _ in Counter(
            t for t in re.findall(r"[a-z]{4,}", joined) if t not in STOP
        ).most_common(6)]
        what = (f"Multiple signals indicate growing activity around "
                f"{cluster_label.lower()}, with recurring themes: {', '.join(top_terms[:4])}.")
        implications = (f"For The Company, this concentrates risk and opportunity in "
                        f"{taxonomy[0] if taxonomy else 'the digital portfolio'}. Watchlist candidates "
                        "should be reviewed within the next 2 weeks.")
        uncertainties = ("Source diversity is limited; corroborate with at least one "
                         "independent vendor or standards body before acting.")
        actions = [
            "Watch: add cluster to weekly trend radar",
            "Experiment: prototype a small evaluation against an internal use case",
            "Engage: brief domain lead and propose 30-day review",
        ]
        return {
            "title": f"Emerging pattern: {cluster_label}",
            "what_happened": what,
            "implications":  implications,
            "uncertainties": uncertainties,
            "time_horizon":  "near" if "incident" in joined or "ga " in joined else "mid",
            "confidence":    "medium",
            "recommended_actions": actions,
            "exec_summary":  f"{what} {implications}",
            "analyst_detail": (f"{what}\n\nKey terms across cluster: {', '.join(top_terms)}.\n\n"
                               f"Implications: {implications}\n\nUncertainties: {uncertainties}"),
        }

    # ── Azure plumbing (placeholder)
    def _azure_chat(self, system: str, user: str, max_tokens: int = 400) -> Optional[str]:
        """Wire up when needed. Kept tiny to avoid a hard dep on the SDK."""
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        key      = os.getenv("AZURE_OPENAI_KEY")
        deploy   = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        version  = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-01-preview")
        if not (endpoint and key and deploy):
            return None
        try:
            import httpx
            url = f"{endpoint.rstrip('/')}/openai/deployments/{deploy}/chat/completions?api-version={version}"
            r = httpx.post(url, headers={"api-key": key, "Content-Type": "application/json"}, json={
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_tokens": max_tokens, "temperature": 0.2,
            }, timeout=30)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            return None


# module singleton
_llm: Optional[LLM] = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM()
    return _llm
