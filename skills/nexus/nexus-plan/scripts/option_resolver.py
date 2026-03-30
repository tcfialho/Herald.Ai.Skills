"""
Nexus Plan - Option Resolver

Manages A/B decisions made during the discovery phase.
Records each decision with rationale and final choice so the plan
generator can reference them and the audit trail is complete.

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
    resolver.save(".nexus/nexus_auth-system/decisions.json")
    md = resolver.to_markdown()
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ------------------------------------------------------------------
# Decision model
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

    def to_markdown_row(self) -> str:
        assumed = " _(auto-assumed)_" if self.auto_assumed else ""
        return f"| {self.question_id} | {self.category} | {self.chosen_text}{assumed} |"


# ------------------------------------------------------------------
# Resolver
# ------------------------------------------------------------------


class OptionResolver:
    """Tracks all A/B decisions for a plan and serialises them to JSON."""

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
    ) -> Decision:
        """Record a resolved decision and return it."""
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
        )
        self._decisions.append(decision)
        return decision

    def record_from_form(self, form: object) -> None:
        """
        Populate decisions from a completed DiscoveryForm.
        Assumes form.questions is a list of DiscoveryQuestion objects.
        """
        for i, q in enumerate(form.questions, 1):
            self.record_decision(
                question_id=f"Q{i}",
                category=q.category,
                question=q.question,
                option_a=q.option_a,
                option_b=q.option_b,
                recommendation=q.recommendation,
                chosen=q.answered if q.answered else q.recommendation,
                rationale=q.rationale,
                auto_assumed=(q.answered is None),
            )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: "str | Path") -> Path:
        """Serialise all decisions to a JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "plan_name": self.plan_name,
            "total_decisions": len(self._decisions),
            "auto_assumed_count": sum(1 for d in self._decisions if d.auto_assumed),
            "decisions": [asdict(d) for d in self._decisions],
        }
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        return p

    @classmethod
    def load(cls, path: "str | Path") -> "OptionResolver":
        """Reconstruct an OptionResolver from a saved JSON file."""
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        resolver = cls(plan_name=payload.get("plan_name", "unknown"))
        for raw in payload.get("decisions", []):
            resolver._decisions.append(Decision(**raw))
        return resolver

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def to_markdown(self) -> str:
        if not self._decisions:
            return "_No decisions recorded yet._"
        lines = [
            f"## 📋 Decisions Log — {self.plan_name}\n",
            "| ID | Category | Chosen |",
            "|----|----------|--------|",
        ]
        lines.extend(d.to_markdown_row() for d in self._decisions)
        auto = sum(1 for d in self._decisions if d.auto_assumed)
        lines += [
            f"\n**Total:** {len(self._decisions)} decisions | "
            f"**Auto-assumed:** {auto}",
        ]
        return "\n".join(lines)

    def get_decisions_by_category(self, category: str) -> list[Decision]:
        return [d for d in self._decisions if d.category == category]

    def get_all_decisions(self) -> list[Decision]:
        return list(self._decisions)

    @property
    def non_recommended_count(self) -> int:
        return sum(1 for d in self._decisions if not d.is_recommended)

    @property
    def auto_assumed_count(self) -> int:
        return sum(1 for d in self._decisions if d.auto_assumed)
