"""
Nexus Hom - Compliance Checker

Verifies that every EARS requirement declared in the spec.md has a
corresponding implementation signal and at least one passing test.

Algorithm:
  1. Parse EARS requirements from .nexus/{plan_name}/spec.md
  2. For each EARS requirement, search for implementation evidence:
     - A function/class/route that semantically relates to the trigger
     - A test file that contains a reference to the behaviour
  3. Report compliance rate and list uncovered requirements

Usage:
    checker = ComplianceChecker(
        plan_path=".nexus/nexus_auth/spec.md",
        project_root=".",
    )
    report = checker.check()
    print(report.to_markdown())
    print(f"Compliance: {report.compliance_pct:.1f}%")
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus_core.file_utils import read_text, list_python_files, list_markdown_files

_EARS_RE = re.compile(
    r"`?(WHEN|WHILE|IF|WHERE)\s+(.+?)(?:\s+THE SYSTEM SHALL|\s+THEN THE SYSTEM SHALL)\s+(.+?)`?$",
    re.IGNORECASE | re.MULTILINE,
)


# ------------------------------------------------------------------
# Data models
# ------------------------------------------------------------------


@dataclass
class RequirementCheck:
    requirement: str
    keyword: str  # WHEN / WHILE / IF / WHERE
    trigger: str
    behaviour: str
    implementation_found: bool = False
    test_found: bool = False
    implementation_evidence: list[str] = field(default_factory=list)
    test_evidence: list[str] = field(default_factory=list)

    @property
    def is_compliant(self) -> bool:
        return self.implementation_found and self.test_found

    @property
    def status(self) -> str:
        if self.is_compliant:
            return "✅ Compliant"
        if self.implementation_found:
            return "⚠️ No Test"
        if self.test_found:
            return "⚠️ No Impl"
        return "❌ Missing"


@dataclass
class ComplianceReport:
    plan_name: str
    total_requirements: int
    compliant_count: int
    checks: list[RequirementCheck] = field(default_factory=list)

    @property
    def compliance_pct(self) -> float:
        if self.total_requirements == 0:
            return 100.0
        return round(self.compliant_count / self.total_requirements * 100, 1)

    @property
    def non_compliant(self) -> list[RequirementCheck]:
        return [c for c in self.checks if not c.is_compliant]

    def to_markdown(self) -> str:
        pct = self.compliance_pct
        emoji = "✅" if pct >= 90 else ("⚠️" if pct >= 70 else "❌")
        lines = [
            f"## {emoji} EARS Compliance — {self.plan_name}\n",
            f"**Compliance Rate:** {pct:.1f}% "
            f"({self.compliant_count}/{self.total_requirements} requirements covered)\n",
            "| Requirement | Status | Impl | Test |",
            "|-------------|--------|------|------|",
        ]
        for chk in self.checks:
            req_short = chk.requirement[:70] + ("..." if len(chk.requirement) > 70 else "")
            impl = ", ".join(chk.implementation_evidence[:2]) or "—"
            test = ", ".join(chk.test_evidence[:2]) or "—"
            lines.append(f"| `{req_short}` | {chk.status} | {impl} | {test} |")

        if self.non_compliant:
            lines += ["", "### ❌ Non-Compliant Requirements (Action Required)\n"]
            for chk in self.non_compliant:
                lines.append(f"- **{chk.requirement}**")
                if not chk.implementation_found:
                    lines.append("  - Missing implementation")
                if not chk.test_found:
                    lines.append("  - Missing test")

        return "\n".join(lines)


# ------------------------------------------------------------------
# Compliance Checker
# ------------------------------------------------------------------


class ComplianceChecker:
    def __init__(self, plan_path: "str | Path", project_root: str = ".") -> None:
        self.plan_path = Path(plan_path)
        self.project_root = Path(project_root).resolve()
        self._plan_name = (
            self.plan_path.parent.name
            if self.plan_path.name.lower() == "spec.md"
            else self.plan_path.stem
        )

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    def check(self) -> ComplianceReport:
        content = read_text(self.plan_path)
        requirements = self._extract_ears(content)
        checks = [self._check_requirement(req) for req in requirements]
        compliant = sum(1 for c in checks if c.is_compliant)
        return ComplianceReport(
            plan_name=self._plan_name,
            total_requirements=len(requirements),
            compliant_count=compliant,
            checks=checks,
        )

    # ------------------------------------------------------------------
    # EARS parsing
    # ------------------------------------------------------------------

    def _extract_ears(self, content: str) -> list[str]:
        """Extract all EARS requirement strings from plan content."""
        matches = _EARS_RE.finditer(content)
        requirements = []
        for match in matches:
            requirements.append(match.group(0).strip().strip("`"))
        return list(dict.fromkeys(requirements))  # deduplicate order-preserving

    # ------------------------------------------------------------------
    # Evidence search
    # ------------------------------------------------------------------

    def _check_requirement(self, requirement: str) -> RequirementCheck:
        match = _EARS_RE.match(requirement)
        if not match:
            return RequirementCheck(
                requirement=requirement,
                keyword="UNKNOWN",
                trigger="",
                behaviour="",
            )

        keyword = match.group(1).upper()
        trigger = match.group(2).strip()
        behaviour = match.group(3).strip()

        # Build search keywords from trigger + behaviour
        search_keywords = self._extract_keywords(trigger + " " + behaviour)

        impl_files, test_files = self._search_evidence(search_keywords)
        return RequirementCheck(
            requirement=requirement,
            keyword=keyword,
            trigger=trigger,
            behaviour=behaviour,
            implementation_found=len(impl_files) > 0,
            test_found=len(test_files) > 0,
            implementation_evidence=impl_files[:3],
            test_evidence=test_files[:3],
        )

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract meaningful words from EARS trigger+behaviour text.
        Splits camelCase and snake_case tokens before filtering stop words so
        that e.g. 'validateCredentials' → ['validate', 'credentials'] and
        'authenticate_user' → ['authenticate', 'user'], reducing false negatives
        when the implementation uses a different naming convention than the spec.
        """
        stop_words = {
            "the", "system", "shall", "when", "while", "where", "then", "this",
            "that", "with", "from", "into", "and", "for", "are", "not", "its",
        }
        # Split camelCase: insertBefore → insert_before
        camel_split = re.sub(r"([a-z])([A-Z])", r"\1_\2", text)
        # Now split on non-alpha boundaries (underscores, spaces, etc.)
        raw_tokens = re.findall(r"[a-zA-Z]{3,}", camel_split.lower())
        return [w for w in raw_tokens if w not in stop_words]

    def _search_evidence(
        self, keywords: list[str]
    ) -> tuple[list[str], list[str]]:
        """Search source and test files for keyword evidence."""
        impl_files: list[str] = []
        test_files: list[str] = []

        if not keywords:
            return impl_files, test_files

        for src_file in self._get_source_files():
            try:
                content = read_text(src_file).lower()
            except OSError:
                continue
            hit_count = sum(1 for kw in keywords if kw in content)
            if hit_count >= max(1, len(keywords) // 3):
                rel = str(src_file.relative_to(self.project_root))
                if self._is_test_file(src_file):
                    test_files.append(rel)
                else:
                    impl_files.append(rel)

        return impl_files, test_files

    def _get_source_files(self) -> list[Path]:
        """Return all Python, TS, JS files excluding venv/node_modules."""
        excluded = {".venv", "venv", "node_modules", "__pycache__", ".temp", ".nexus"}
        result = []
        for ext in ("*.py", "*.ts", "*.js", "*.go", "*.cs", "*.rs"):
            for fp in self.project_root.rglob(ext):
                if not any(p in excluded for p in fp.relative_to(self.project_root).parts):
                    result.append(fp)
        return result

    def _is_test_file(self, path: Path) -> bool:
        name = path.name.lower()
        parts = path.parts
        return (
            name.startswith("test_")
            or name.endswith("_test.py")
            or name.endswith(".test.ts")
            or name.endswith(".spec.ts")
            or name.endswith(".test.js")
            or any(p in ("tests", "test", "__tests__", "spec") for p in parts)
        )


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: compliance_checker.py <spec.md> [project_root]")
        sys.exit(1)
    plan = sys.argv[1]
    root = sys.argv[2] if len(sys.argv) > 2 else "."
    checker = ComplianceChecker(plan_path=plan, project_root=root)
    report = checker.check()
    print(report.to_markdown())
    sys.exit(0 if report.compliance_pct >= 90 else 1)

