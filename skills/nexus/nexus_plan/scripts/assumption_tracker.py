"""
Nexus Plan - Assumption Tracker

Tracks every assumption made during plan phase so they can be:
  - Audited before /dev begins
  - Flagged if high-risk
  - Re-validated after /review

An assumption is a decision taken without explicit user confirmation.
Auto-assumptions (from timeout/default) are always tracked here.

Usage:
    tracker = AssumptionTracker(plan_name="auth-system")
    tracker.add("Primary DB is PostgreSQL", category="Infrastructure", confidence=0.9)
    tracker.save(".nexus/nexus_auth-system/assumptions.json")
    print(tracker.to_markdown())
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


RiskLevel = Literal["low", "medium", "high"]
ConfirmationStatus = Literal["assumed", "confirmed", "contradicted"]


# ------------------------------------------------------------------
# Assumption model
# ------------------------------------------------------------------


@dataclass
class Assumption:
    statement: str
    category: str  # e.g. "Infrastructure", "Auth", "Business Logic"
    confidence: float  # 0.0 – 1.0 (auto-assumed = recommendation confidence)
    risk: RiskLevel = "low"
    status: ConfirmationStatus = "assumed"
    source: str = "auto"  # "auto" | "discovery_form" | "user_explicit"
    validated_at: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str = ""

    @property
    def risk_emoji(self) -> str:
        return {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(self.risk, "⚪")

    @property
    def status_emoji(self) -> str:
        return {
            "assumed": "⚠️",
            "confirmed": "✅",
            "contradicted": "❌",
        }.get(self.status, "❓")

    def confirm(self) -> None:
        self.status = "confirmed"
        self.validated_at = datetime.now(timezone.utc).isoformat()

    def contradict(self, notes: str = "") -> None:
        self.status = "contradicted"
        self.validated_at = datetime.now(timezone.utc).isoformat()
        if notes:
            self.notes = notes


# ------------------------------------------------------------------
# Tracker
# ------------------------------------------------------------------


class AssumptionTracker:
    """Stores and reports all planning assumptions for a given plan."""

    def __init__(self, plan_name: str) -> None:
        self.plan_name = plan_name
        self._assumptions: list[Assumption] = []

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(
        self,
        statement: str,
        category: str = "General",
        confidence: float = 0.8,
        risk: RiskLevel = "low",
        source: str = "auto",
        notes: str = "",
    ) -> Assumption:
        """Record a new assumption and return it."""
        assumption = Assumption(
            statement=statement,
            category=category,
            confidence=confidence,
            risk=risk,
            source=source,
            notes=notes,
        )
        self._assumptions.append(assumption)
        return assumption

    def confirm(self, index: int) -> None:
        """Confirm assumption at 1-based index."""
        self._get(index).confirm()

    def contradict(self, index: int, notes: str = "") -> None:
        """Mark assumption at 1-based index as contradicted."""
        self._get(index).contradict(notes)

    # ------------------------------------------------------------------
    # Import helpers
    # ------------------------------------------------------------------

    def import_from_resolver(self, resolver: object) -> None:
        """
        Automatically populate assumptions from an OptionResolver's auto-assumed decisions.
        """
        for decision in resolver.get_all_decisions():
            if decision.auto_assumed:
                self.add(
                    statement=f"{decision.category}: {decision.chosen_text}",
                    category=decision.category,
                    confidence=0.75,
                    risk="medium",
                    source="auto",
                    notes=decision.rationale,
                )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: "str | Path") -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "plan_name": self.plan_name,
            "total": len(self._assumptions),
            "high_risk": sum(1 for a in self._assumptions if a.risk == "high"),
            "unconfirmed": sum(1 for a in self._assumptions if a.status == "assumed"),
            "assumptions": [asdict(a) for a in self._assumptions],
        }
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        return p

    @classmethod
    def load(cls, path: "str | Path") -> "AssumptionTracker":
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        tracker = cls(plan_name=payload.get("plan_name", "unknown"))
        for raw in payload.get("assumptions", []):
            # Handle older files that may not have all fields
            raw.setdefault("validated_at", "")
            raw.setdefault("notes", "")
            tracker._assumptions.append(Assumption(**raw))
        return tracker

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def to_markdown(self) -> str:
        if not self._assumptions:
            return "_No assumptions recorded._"
        lines = [
            f"## 📌 Assumptions — {self.plan_name}\n",
            "| # | Category | Statement | Risk | Status | Confidence |",
            "|---|----------|-----------|------|--------|------------|",
        ]
        for i, a in enumerate(self._assumptions, 1):
            conf_pct = f"{int(a.confidence * 100)}%"
            lines.append(
                f"| {i} | {a.category} | {a.statement} | "
                f"{a.risk_emoji} {a.risk} | {a.status_emoji} {a.status} | {conf_pct} |"
            )

        high_risk = [a for a in self._assumptions if a.risk == "high"]
        if high_risk:
            lines += ["", "### ⚠️ High-Risk Assumptions (require stakeholder sign-off)\n"]
            for a in high_risk:
                lines.append(f"- **{a.category}:** {a.statement} _{a.notes}_")

        return "\n".join(lines)

    def has_high_risk_unconfirmed(self) -> bool:
        return any(
            a.risk == "high" and a.status == "assumed" for a in self._assumptions
        )

    def get_all(self) -> list[Assumption]:
        return list(self._assumptions)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get(self, index: int) -> Assumption:
        if not (1 <= index <= len(self._assumptions)):
            raise IndexError(f"Assumption index {index} out of range (1–{len(self._assumptions)}).")
        return self._assumptions[index - 1]
