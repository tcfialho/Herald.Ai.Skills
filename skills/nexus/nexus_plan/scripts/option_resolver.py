"""
Nexus Plan - Option Resolver (Unified Decisions + Assumptions)

Single source of truth for all planning decisions.
Explicit user choices are stored as decisions.
Unanswered questions auto-assumed as recommendations are flagged as assumptions.

The OptionResolver no longer writes a standalone JSON file.
Instead it produces:
  1. Rich Markdown (injected into spec.md by PlanGenerator)
  2. A compact decision manifest (consumed by StoryGenerator and TaskBreaker
     to propagate relevant decisions into each story/task context)

Usage:
    resolver = OptionResolver(plan_name="auth-system")
    resolver.record_decision(
        question_id="Q1",
        category="Persistence",
        question="What is the data persistence strategy?",
        option_a="Relational DB (PostgreSQL)",
        option_b="Document store (MongoDB)",
        recommendation="A",
        chosen="A",
        rationale="Team already uses PostgreSQL in production.",
    )
    md = resolver.to_markdown()
    manifest = resolver.to_manifest()  # compact dict for downstream propagation
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional


RiskLevel = Literal["low", "medium", "high"]


# ------------------------------------------------------------------
# Decision model (unified: explicit + auto-assumed)
# ------------------------------------------------------------------


@dataclass
class Decision:
    question_id: str
    category: str
    question: str
    option_a: str
    option_b: str
    recommendation: str  # "A" or "B"
    chosen: str  # "A", "B", or custom text
    rationale: str
    auto_assumed: bool = False
    risk: RiskLevel = "low"
    confidence: float = 1.0  # 1.0 for explicit user choice, 0.75 for auto-assumed
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_recommended(self) -> bool:
        """True if the user chose the recommended option (or it was auto-assumed)."""
        return self.chosen == self.recommendation

    @property
    def chosen_text(self) -> str:
        """Return the human-readable text of the chosen option."""
        if self.chosen == "A":
            return self.option_a
        if self.chosen == "B":
            return self.option_b
        return self.chosen  # custom answer

    @property
    def risk_emoji(self) -> str:
        return {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(self.risk, "⚪")

    def to_compact(self) -> dict:
        """Minimal representation for downstream propagation (stories/tasks)."""
        label = " _(auto-assumed)_" if self.auto_assumed else ""
        return {
            "id": self.question_id,
            "category": self.category,
            "question": self.question,
            "chosen": self.chosen_text,
            "rationale": self.rationale,
            "auto_assumed": self.auto_assumed,
            "risk": self.risk,
        }


# ------------------------------------------------------------------
# Resolver
# ------------------------------------------------------------------


class OptionResolver:
    """Tracks all planning decisions (explicit + auto-assumed) for a plan."""

    def __init__(self, plan_name: str) -> None:
        self.plan_name = plan_name
        self._decisions: list[Decision] = []

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_decision(
        self,
        question_id: str,
        category: str,
        question: str,
        option_a: str,
        option_b: str,
        recommendation: str,
        chosen: str,
        rationale: str,
        auto_assumed: bool = False,
        risk: RiskLevel = "low",
    ) -> Decision:
        """Record a resolved decision and return it."""
        confidence = 0.75 if auto_assumed else 1.0
        if auto_assumed and risk == "low":
            risk = "medium"

        decision = Decision(
            question_id=question_id,
            category=category,
            question=question,
            option_a=option_a,
            option_b=option_b,
            recommendation=recommendation,
            chosen=chosen,
            rationale=rationale,
            auto_assumed=auto_assumed,
            risk=risk,
            confidence=confidence,
        )
        self._decisions.append(decision)
        return decision

    def record_from_form(self, form: object) -> None:
        """
        Populate decisions from a completed DiscoveryForm.
        Assumes form.questions is a list of DiscoveryQuestion objects.
        """
        for i, q in enumerate(form.questions, 1):
            is_auto = q.answered is None
            self.record_decision(
                question_id=f"Q{i}",
                category=q.category,
                question=q.question,
                option_a=q.option_a,
                option_b=q.option_b,
                recommendation=q.recommendation,
                chosen=q.answered if q.answered else q.recommendation,
                rationale=q.rationale,
                auto_assumed=is_auto,
            )

    # ------------------------------------------------------------------
    # Reporting (Rich Markdown for spec.md)
    # ------------------------------------------------------------------

    def to_markdown(self) -> str:
        if not self._decisions:
            return "_No decisions recorded yet._"

        lines = [
            f"## 📋 Decisions Log — {self.plan_name}\n",
            "| ID | Category | Question | Chosen | Rationale | Risk |",
            "|----|----------|----------|--------|-----------|------|",
        ]
        for d in self._decisions:
            assumed_tag = " _(auto)_" if d.auto_assumed else ""
            lines.append(
                f"| {d.question_id} | {d.category} | {d.question} "
                f"| {d.chosen_text}{assumed_tag} | {d.rationale} | {d.risk_emoji} {d.risk} |"
            )

        auto_count = sum(1 for d in self._decisions if d.auto_assumed)
        high_risk = sum(1 for d in self._decisions if d.risk == "high")
        lines += [
            f"\n**Total:** {len(self._decisions)} decisions | "
            f"**Auto-assumed:** {auto_count} | "
            f"**High-risk:** {high_risk}",
        ]

        if auto_count > 0:
            lines += [
                "",
                "> ⚠️ **Auto-assumed decisions** were not explicitly answered by the user. "
                "The recommended option was applied. Review before `/dev`.",
            ]

        if high_risk > 0:
            lines += [
                "",
                "> 🔴 **High-risk decisions** require stakeholder sign-off before execution.",
            ]

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Manifest (compact for downstream propagation)
    # ------------------------------------------------------------------

    def to_manifest(self) -> list[dict]:
        """Return a compact list of decisions for injection into stories/tasks."""
        return [d.to_compact() for d in self._decisions]

    def get_decisions_by_category(self, category: str) -> list[Decision]:
        return [d for d in self._decisions if d.category == category]

    def get_decisions_for_categories(self, categories: list[str]) -> list[Decision]:
        """Get decisions matching any of the given categories."""
        cat_set = set(categories)
        return [d for d in self._decisions if d.category in cat_set]

    def get_all_decisions(self) -> list[Decision]:
        return list(self._decisions)

    def get_auto_assumed(self) -> list[Decision]:
        """Return only auto-assumed decisions (the old 'assumptions')."""
        return [d for d in self._decisions if d.auto_assumed]

    @property
    def non_recommended_count(self) -> int:
        return sum(1 for d in self._decisions if not d.is_recommended)

    @property
    def auto_assumed_count(self) -> int:
        return sum(1 for d in self._decisions if d.auto_assumed)

    def has_high_risk_unconfirmed(self) -> bool:
        return any(
            d.risk == "high" and d.auto_assumed for d in self._decisions
        )
