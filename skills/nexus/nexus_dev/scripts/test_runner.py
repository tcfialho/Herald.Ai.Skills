"""
Nexus Dev - Test Runner

Executes the project's test suite via subprocess and captures structured
output (pass/fail counts, coverage %, duration).

Supported test frameworks (auto-detected):
  - pytest   (Python)
  - jest     (JavaScript/TypeScript)
  - go test  (Go)
  - dotnet test (.NET)
  - cargo test (Rust)

Results are written to .temp/test_results.json for /review to consume.

Usage:
    runner = TestRunner(project_root=".")
    result = runner.run()
    if not result.passed:
        print(result.summary)
    runner.save_result(".temp/test_results.json")
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ------------------------------------------------------------------
# Result model
# ------------------------------------------------------------------


@dataclass
class TestResult:
    framework: str
    passed: bool
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    coverage_pct: Optional[float] = None
    duration_seconds: float = 0.0
    raw_output: str = ""
    error_summary: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        cov = f" | coverage={self.coverage_pct:.1f}%" if self.coverage_pct is not None else ""
        return (
            f"[{status}] {self.framework}: "
            f"{self.passed_tests}/{self.total_tests} tests passed "
            f"({self.failed_tests} failed, {self.skipped_tests} skipped)"
            f"{cov} in {self.duration_seconds:.2f}s"
        )

    def to_markdown(self) -> str:
        status_emoji = "✅" if self.passed else "❌"
        lines = [
            f"### {status_emoji} Test Results ({self.framework})\n",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Status | {'PASS' if self.passed else 'FAIL'} |",
            f"| Total | {self.total_tests} |",
            f"| Passed | {self.passed_tests} |",
            f"| Failed | {self.failed_tests} |",
            f"| Skipped | {self.skipped_tests} |",
        ]
        if self.coverage_pct is not None:
            lines.append(f"| Coverage | {self.coverage_pct:.1f}% |")
        lines.append(f"| Duration | {self.duration_seconds:.2f}s |")
        if self.error_summary:
            lines += ["", f"**Errors:**\n```\n{self.error_summary[:1000]}\n```"]
        return "\n".join(lines)


# ------------------------------------------------------------------
# Test Runner
# ------------------------------------------------------------------


class TestRunner:
    def __init__(self, project_root: str = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self._last_result: Optional[TestResult] = None

    # ------------------------------------------------------------------
    # Auto-detect framework
    # ------------------------------------------------------------------

    def detect_framework(self) -> str:
        """Detect the test framework based on project files."""
        root = self.project_root
        if (root / "pytest.ini").exists() or (root / "pyproject.toml").exists() or \
                (root / "setup.cfg").exists() or list(root.rglob("test_*.py")):
            return "pytest"
        if (root / "package.json").exists():
            with open(root / "package.json", encoding="utf-8") as fh:
                pkg = json.load(fh)
            if "jest" in pkg.get("devDependencies", {}) or "jest" in pkg.get("dependencies", {}):
                return "jest"
        if list(root.rglob("*.go")):
            return "go"
        if list(root.glob("**/*.csproj")):
            return "dotnet"
        if (root / "Cargo.toml").exists():
            return "cargo"
        return "unknown"

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self, framework: Optional[str] = None, extra_args: list[str] = None) -> TestResult:
        """Detect and run the test suite. Returns a structured TestResult."""
        resolved_framework = framework or self.detect_framework()
        command = self._build_command(resolved_framework, extra_args or [])
        if not command:
            return TestResult(
                framework=resolved_framework,
                passed=False,
                error_summary=f"Unknown test framework '{resolved_framework}'. "
                              "Add a pytest.ini, package.json (jest), or go.mod.",
            )

        start = time.perf_counter()
        try:
            proc = subprocess.run(
                command,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            return TestResult(
                framework=resolved_framework,
                passed=False,
                error_summary="Test suite timed out after 300 seconds.",
            )
        duration = time.perf_counter() - start

        raw_output = proc.stdout + "\n" + proc.stderr
        result = self._parse_output(resolved_framework, raw_output, proc.returncode, duration)
        self._last_result = result
        return result

    def _build_command(self, framework: str, extra_args: list[str]) -> list[str]:
        commands = {
            "pytest": ["python", "-m", "pytest", "--tb=short", "-q", "--cov=.", "--cov-report=term-missing"],
            "jest": ["npx", "jest", "--coverage", "--ci"],
            "go": ["go", "test", "./...", "-cover", "-v"],
            "dotnet": ["dotnet", "test", "--logger", "console;verbosity=normal"],
            "cargo": ["cargo", "test"],
        }
        base = commands.get(framework)
        if base is None:
            return []
        return base + extra_args

    # ------------------------------------------------------------------
    # Output parsers
    # ------------------------------------------------------------------

    def _parse_output(
        self, framework: str, output: str, returncode: int, duration: float
    ) -> TestResult:
        parsers = {
            "pytest": self._parse_pytest,
            "jest": self._parse_jest,
            "go": self._parse_go,
        }
        parser = parsers.get(framework, self._parse_generic)
        result = parser(output)
        result.framework = framework
        result.duration_seconds = duration
        result.raw_output = output[:5000]  # cap stored output
        result.passed = returncode == 0
        return result

    def _parse_pytest(self, output: str) -> TestResult:
        result = TestResult(framework="pytest", passed=True)
        summary_re = re.search(r"=+\s*(.+?)\s+in\s+[\d.]+s\s*=+\s*$", output, re.MULTILINE)
        summary_text = summary_re.group(1) if summary_re else output

        for label, attr_name in (
            ("passed", "passed_tests"),
            ("failed", "failed_tests"),
            ("skipped", "skipped_tests"),
        ):
            count_match = re.search(rf"(\d+)\s+{label}\b", summary_text)
            if count_match:
                setattr(result, attr_name, int(count_match.group(1)))

        result.total_tests = result.passed_tests + result.failed_tests + result.skipped_tests

        cov_re = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
        if cov_re:
            result.coverage_pct = float(cov_re.group(1))

        if result.failed_tests > 0 or "ERROR" in output:
            fail_lines = [l for l in output.splitlines() if "FAILED" in l or "ERROR" in l]
            result.error_summary = "\n".join(fail_lines[:20])
        return result

    def _parse_jest(self, output: str) -> TestResult:
        result = TestResult(framework="jest", passed=True)

        # Parse each counter independently: Jest emits a variable subset of
        # "X failed", "Y skipped", "Z todo", "W passed", "N total" in any order.
        def _extract_counter(label: str) -> int:
            m = re.search(rf"(\d+)\s+{label}", output)
            return int(m.group(1)) if m else 0

        result.failed_tests = _extract_counter("failed")
        result.passed_tests = _extract_counter("passed")
        result.skipped_tests = _extract_counter("skipped") + _extract_counter("todo")
        result.total_tests = _extract_counter("total")
        # Recompute total from parts when the "total" line is absent
        if result.total_tests == 0:
            result.total_tests = result.passed_tests + result.failed_tests + result.skipped_tests

        cov_re = re.search(r"All files\s+\|\s+[\d.]+\s+\|\s+[\d.]+\s+\|\s+[\d.]+\s+\|\s+([\d.]+)", output)
        if cov_re:
            result.coverage_pct = float(cov_re.group(1))
        return result

    def _parse_go(self, output: str) -> TestResult:
        result = TestResult(framework="go", passed=True)
        pass_count = len(re.findall(r"--- PASS:", output))
        fail_count = len(re.findall(r"--- FAIL:", output))
        result.passed_tests = pass_count
        result.failed_tests = fail_count
        result.total_tests = pass_count + fail_count
        cov_re = re.search(r"coverage:\s+([\d.]+)%", output)
        if cov_re:
            result.coverage_pct = float(cov_re.group(1))
        return result

    def _parse_generic(self, output: str) -> TestResult:
        result = TestResult(framework="generic", passed=True)
        result.error_summary = output[:500] if output else ""
        return result

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_result(self, path: "str | Path") -> Optional[Path]:
        if self._last_result is None:
            return None
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(asdict(self._last_result), fh, indent=2, ensure_ascii=False)
        return p

    @property
    def last_result(self) -> Optional[TestResult]:
        return self._last_result


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    runner = TestRunner(project_root=root)
    result = runner.run()
    print(result.summary)
    output_path = Path(root) / ".temp" / "test_results.json"
    runner.save_result(output_path)
    print(f"Results written to {output_path}")
    sys.exit(0 if result.passed else 1)
