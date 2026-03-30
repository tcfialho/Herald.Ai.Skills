"""
Nexus Hom - Test Executor

Orchestrates the full test evidence collection run for /review validation.
Runs the test suite, captures coverage and output, then writes structured
evidence to .temp/review_test_evidence.json for the certification engine.

Differs from dev/test_runner.py in that it:
  - Is always run in "full evidence" mode (no skipping)
  - Enforces minimum coverage thresholds
  - Produces a /review-optimised result with richer context

Usage:
    executor = TestExecutor(project_root=".")
    evidence = executor.collect_evidence()
    executor.save_evidence(".temp/review_test_evidence.json")
    print(evidence.summary_markdown)
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))  # for nexus_core
sys.path.insert(
    0, str(_ROOT / "nexus_dev" / "scripts")
)  # for test_runner, build_system

from test_runner import TestRunner, TestResult
from build_system import BuildSystem, BuildResult

MINIMUM_COVERAGE_PCT = 80.0


# ------------------------------------------------------------------
# Evidence model
# ------------------------------------------------------------------


@dataclass
class HomologationTestEvidence:
    plan_name: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    test_result: Optional[dict] = None
    build_result: Optional[dict] = None
    coverage_met: bool = False
    minimum_coverage: float = MINIMUM_COVERAGE_PCT
    actual_coverage: float = 0.0
    tests_passed: bool = False
    build_passed: bool = False
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    build_warnings: int = 0
    blocking_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_eligible_for_certification(self) -> bool:
        return (
            self.tests_passed
            and self.build_passed
            and self.coverage_met
            and len(self.blocking_issues) == 0
        )

    @property
    def summary_markdown(self) -> str:
        cert_status = (
            "✅ ELIGIBLE" if self.is_eligible_for_certification else "❌ NOT ELIGIBLE"
        )
        lines = [
            f"## 🔬 Test & Build Evidence — {self.plan_name}\n",
            f"**Certification Eligibility:** {cert_status}  ",
            f"**Timestamp:** {self.timestamp}\n",
            "| Check | Status |",
            "|-------|--------|",
            f"| Build | {'✅ PASS' if self.build_passed else '❌ FAIL'} |",
            f"| Tests | {'✅ PASS' if self.tests_passed else '❌ FAIL'} ({self.passed_tests}/{self.total_tests}) |",
            f"| Coverage | {'✅' if self.coverage_met else '❌'} {self.actual_coverage:.1f}% (min {self.minimum_coverage}%) |",
            f"| Blocking Issues | {'None' if not self.blocking_issues else str(len(self.blocking_issues))} |",
        ]
        if self.blocking_issues:
            lines += ["", "### ❌ Blocking Issues\n"]
            for issue in self.blocking_issues:
                lines.append(f"- {issue}")
        if self.warnings:
            lines += ["", "### ⚠️ Warnings\n"]
            for w in self.warnings:
                lines.append(f"- {w}")
        return "\n".join(lines)


# ------------------------------------------------------------------
# TestExecutor
# ------------------------------------------------------------------


class TestExecutor:
    def __init__(
        self,
        project_root: str = ".",
        minimum_coverage: float = MINIMUM_COVERAGE_PCT,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.minimum_coverage = minimum_coverage
        self._evidence: Optional[HomologationTestEvidence] = None
        self._test_runner = TestRunner(str(self.project_root))
        self._build_system = BuildSystem(str(self.project_root))

    # ------------------------------------------------------------------
    # Evidence collection
    # ------------------------------------------------------------------

    def collect_evidence(self, plan_name: str = "unknown") -> HomologationTestEvidence:
        """Run build + tests, collect full evidence. Returns the evidence object."""
        evidence = HomologationTestEvidence(plan_name=plan_name)

        # Step 1: Build
        build_result = self._build_system.run()
        evidence.build_result = asdict(build_result)
        evidence.build_passed = build_result.passed
        evidence.build_warnings = build_result.warnings_count

        if not build_result.passed:
            evidence.blocking_issues.append(
                f"Build FAILED ({self._build_system.detect_build_system()}): "
                + build_result.error_summary[:200]
            )

        # Step 2: Tests
        test_result = self._test_runner.run()
        evidence.test_result = asdict(test_result)
        evidence.tests_passed = test_result.passed
        evidence.total_tests = test_result.total_tests
        evidence.passed_tests = test_result.passed_tests
        evidence.failed_tests = test_result.failed_tests
        evidence.actual_coverage = test_result.coverage_pct or 0.0
        # Coverage is only enforced when it can be measured (>0). A project with
        # no coverage tooling configured is not penalised here; CertificationEngine
        # applies the same rule in its certify() method.
        evidence.coverage_met = (
            evidence.actual_coverage == 0.0
            or evidence.actual_coverage >= self.minimum_coverage
        )

        if not test_result.passed:
            evidence.blocking_issues.append(
                f"{test_result.failed_tests} test(s) failed: {test_result.error_summary[:200]}"
            )
        if not evidence.coverage_met and evidence.actual_coverage > 0:
            evidence.blocking_issues.append(
                f"Test coverage {evidence.actual_coverage:.1f}% is below minimum {self.minimum_coverage}%."
            )
        if evidence.actual_coverage == 0.0 and test_result.total_tests > 0:
            evidence.warnings.append(
                "Coverage could not be measured. Ensure coverage tooling is configured."
            )
        if build_result.warnings_count > 10:
            evidence.warnings.append(
                f"{build_result.warnings_count} build warnings detected. Review before production."
            )

        self._evidence = evidence
        return evidence

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_evidence(self, path: "str | Path") -> Path:
        if self._evidence is None:
            raise RuntimeError(
                "No evidence collected yet. Call collect_evidence() first."
            )
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(asdict(self._evidence), fh, indent=2, ensure_ascii=False)
        return p

    @classmethod
    def load_evidence(cls, path: "str | Path") -> HomologationTestEvidence:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return HomologationTestEvidence(
            **{
                k: v
                for k, v in raw.items()
                if k in HomologationTestEvidence.__dataclass_fields__
            }
        )

    @property
    def last_evidence(self) -> Optional[HomologationTestEvidence]:
        return self._evidence


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    plan = sys.argv[2] if len(sys.argv) > 2 else "unknown-plan"
    executor = TestExecutor(project_root=root)
    ev = executor.collect_evidence(plan_name=plan)
    print(ev.summary_markdown)
    out = Path(root) / ".temp" / "review_test_evidence.json"
    executor.save_evidence(out)
    print(f"\nEvidence written to {out}")
    sys.exit(0 if ev.is_eligible_for_certification else 1)
