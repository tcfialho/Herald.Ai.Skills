"""
Nexus Hom - Quality Gates

Implements the 5-Dimension Quality Assessment derived from AIOS Core.

Dimensions and weights:
  Accuracy     (25%) — Does implementation faithfully reflect the EARS requirements?
  Completeness (25%) — Are all features implemented? Are edge cases tested?
  Consistency  (20%) — No contradictions? Patterns followed? IDs valid?
  Feasibility  (15%) — Technically sound, secure, performant?
  Alignment    (15%) — Aligned with stack conventions and best practices?

Verdict logic:
  BLOCKED       — ANY dimension score ≤ 2
  NEEDS_REVISION — Average < 4.0 OR any dimension < 3.0
  APPROVED      — Average ≥ 4.0 AND all dimensions ≥ 3.0

Usage:
    gates = QualityGates()
    gates.set_score("accuracy", 4)
    gates.set_score("completeness", 4)
    gates.set_score("consistency", 4)
    gates.set_score("feasibility", 5)
    gates.set_score("alignment", 4)
    print(gates.verdict)         # APPROVED
    print(gates.weighted_score)  # 4.25
    print(gates.to_markdown())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Verdict = Literal["APPROVED", "NEEDS_REVISION", "BLOCKED"]

DIMENSION_WEIGHTS = {
    "accuracy": 0.25,
    "completeness": 0.25,
    "consistency": 0.20,
    "feasibility": 0.15,
    "alignment": 0.15,
}

DIMENSION_DESCRIPTIONS = {
    "accuracy": "Implementation responds faithfully to the EARS requirements",
    "completeness": "All features implemented; edge cases handled and tested",
    "consistency": "No contradictions; design coherent with existing codebase",
    "feasibility": "Technically viable, secure, and performant in production",
    "alignment": "Follows project conventions, stack best practices, OWASP",
}

SCORE_GUIDE = {
    1: "Critical gap — fundamental requirement missing",
    2: "Major gap — significant feature incomplete",
    3: "Minor gap — small issues, non-critical",
    4: "Good — meets expectations with small observations",
    5: "Excellent — exceeds expectations",
}


# ------------------------------------------------------------------
# Issue model
# ------------------------------------------------------------------


@dataclass
class QualityIssue:
    dimension: str
    severity: Literal["critical", "major", "minor", "info"]
    description: str
    location: str = ""
    remediation: str = ""


# ------------------------------------------------------------------
# Quality Gates
# ------------------------------------------------------------------


class QualityGates:
    def __init__(self) -> None:
        self._scores: dict[str, int] = {}
        self._notes: dict[str, str] = {}
        self.issues: list[QualityIssue] = []

    # ------------------------------------------------------------------
    # Setters
    # ------------------------------------------------------------------

    def set_score(self, dimension: str, score: int, notes: str = "") -> None:
        if dimension not in DIMENSION_WEIGHTS:
            raise ValueError(
                f"Unknown dimension '{dimension}'. Valid: {list(DIMENSION_WEIGHTS.keys())}"
            )
        if not 1 <= score <= 5:
            raise ValueError(f"Score must be 1–5, got {score}.")
        self._scores[dimension] = score
        if notes:
            self._notes[dimension] = notes

    def add_issue(
        self,
        dimension: str,
        severity: Literal["critical", "major", "minor", "info"],
        description: str,
        location: str = "",
        remediation: str = "",
    ) -> None:
        self.issues.append(
            QualityIssue(
                dimension=dimension,
                severity=severity,
                description=description,
                location=location,
                remediation=remediation,
            )
        )

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def weighted_score(self) -> float:
        if not self._all_scored:
            return 0.0
        return sum(
            self._scores[dim] * weight
            for dim, weight in DIMENSION_WEIGHTS.items()
        )

    @property
    def _all_scored(self) -> bool:
        return all(dim in self._scores for dim in DIMENSION_WEIGHTS)

    @property
    def verdict(self) -> Verdict:
        if not self._all_scored:
            raise RuntimeError("Not all 5 dimensions have been scored. Call set_score() for each.")
        if any(score <= 2 for score in self._scores.values()):
            return "BLOCKED"
        if self.weighted_score < 4.0 or any(score < 3 for score in self._scores.values()):
            return "NEEDS_REVISION"
        return "APPROVED"

    @property
    def can_go_to_production(self) -> bool:
        return self.verdict == "APPROVED"

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def to_markdown(self) -> str:
        if not self._all_scored:
            return "_Not all dimensions scored yet._"
        verdict = self.verdict
        verdict_emoji = {"APPROVED": "✅", "NEEDS_REVISION": "⚠️", "BLOCKED": "❌"}[verdict]

        lines = [
            f"## {verdict_emoji} Quality Gate Assessment\n",
            "| Dimension | Weight | Score | Guide | Notes |",
            "|-----------|--------|-------|-------|-------|",
        ]
        for dim, weight in DIMENSION_WEIGHTS.items():
            score = self._scores.get(dim, "?")
            guide = SCORE_GUIDE.get(score, "")
            notes = self._notes.get(dim, "")
            pct = f"{int(weight * 100)}%"
            lines.append(f"| {dim.title()} | {pct} | **{score}/5** | {guide} | {notes} |")

        lines += [
            "",
            f"**Weighted Score:** {self.weighted_score:.2f}/5.0  ",
            f"**Verdict:** `{verdict}` {verdict_emoji}  ",
            f"**Ready for Production:** {'YES' if self.can_go_to_production else 'NO'}",
        ]

        if self.issues:
            lines += ["", "### Issues Found\n"]
            severity_order = {"critical": 0, "major": 1, "minor": 2, "info": 3}
            sorted_issues = sorted(self.issues, key=lambda i: severity_order.get(i.severity, 4))
            lines += [
                "| Dimension | Severity | Description | Location | Remediation |",
                "|-----------|----------|-------------|----------|-------------|",
            ]
            for issue in sorted_issues:
                lines.append(
                    f"| {issue.dimension} | {issue.severity} | {issue.description} "
                    f"| {issue.location or '—'} | {issue.remediation or '—'} |"
                )

        return "\n".join(lines)

    def to_summary_line(self) -> str:
        return (
            f"Quality Gates: {self.weighted_score:.2f}/5.0 → {self.verdict} | "
            + " | ".join(
                f"{dim.title()}={self._scores.get(dim, '?')}"
                for dim in DIMENSION_WEIGHTS
            )
        )

    # ------------------------------------------------------------------
    # Automated quick-scoring from evidence
    # ------------------------------------------------------------------

    def auto_score_from_evidence(self, evidence: "HomologationEvidence") -> None:
        """
        Compute approximate scores based on objective HomologationEvidence metrics.
        Human reviewer should adjust these before finalising.
        """
        # Accuracy — based on EARS compliance rate
        ears_pct = float(
            getattr(evidence, "ears_compliance_pct", getattr(evidence, "compliance_pct", 0.0))
            or 0.0
        )
        self.set_score("accuracy", _pct_to_score(ears_pct), f"EARS compliance: {ears_pct:.0f}%")

        # Completeness — based on test coverage
        cov = float(
            getattr(evidence, "test_coverage_pct", getattr(evidence, "actual_coverage", 0.0))
            or 0.0
        )
        self.set_score("completeness", _pct_to_score(cov), f"Test coverage: {cov:.0f}%")

        # Consistency — build + no failed tests → assume 4 if build passes
        build_ok = evidence.build_passed
        self.set_score("consistency", 4 if build_ok else 2, "Build " + ("passed" if build_ok else "FAILED"))

        # Feasibility — all tests pass → default 4; failing → 2
        tests_ok = evidence.tests_passed
        self.set_score("feasibility", 4 if tests_ok else 2, "Tests " + ("passing" if tests_ok else "FAILING"))

        # Alignment — warnings count heuristic
        warnings = getattr(evidence, "build_warnings_count", None)
        if warnings is None:
            warnings = getattr(evidence, "build_warnings", 0)
        warnings = int(warnings or 0)
        alignment_score = 5 if warnings == 0 else (4 if warnings < 5 else (3 if warnings < 15 else 2))
        self.set_score("alignment", alignment_score, f"{warnings} build warnings")


def _pct_to_score(pct: float) -> int:
    if pct >= 95:
        return 5
    if pct >= 80:
        return 4
    if pct >= 60:
        return 3
    if pct >= 40:
        return 2
    return 1


# ------------------------------------------------------------------
# Evidence container (injected by /review pipeline)
# ------------------------------------------------------------------


@dataclass
class HomologationEvidence:
    ears_compliance_pct: float = 0.0
    test_coverage_pct: float = 0.0
    build_passed: bool = False
    tests_passed: bool = False
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    build_warnings_count: int = 0
    security_scan_clean: bool = True
    docs_present: bool = True
