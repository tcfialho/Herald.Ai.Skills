"""
Nexus Core - Submit Gate (Evidence Before Claims)

Controls task completion state transitions. The AI agent is PROHIBITED from
mutating plan_state.json directly to mark tasks as "completed". Instead, the
agent must invoke this gate, which:

  1. Reads the verify_cmd from tasks.json (set at planning time by TaskBreaker)
  2. Scans implementation files for mock/placeholder code
  3. Validates test files reference implementation files (anti-dummy-test)
  4. Executes the verify_cmd in a hermetic subprocess
  5. Only on full success: transitions state to "completed"

The gate is language/stack agnostic — the verify_cmd can be any shell command
(pytest, vitest, dotnet test, go test, cargo test, javac + junit, etc.)

Usage (from AI agent):
    python -m nexus_core.submit_gate --plan my_plan --task TASK-001

Usage (programmatic):
    from nexus_core.submit_gate import SubmitGate
    gate = SubmitGate(project_root=".", plan_name="my_plan")
    result = gate.submit("TASK-001")
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .state_manager import NexusStateManager
from .validation import validate_no_mock_code, ValidationResult
from .file_utils import read_text

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

MAX_CONSECUTIVE_FAILURES = 3
VERIFY_TIMEOUT_SECONDS = 120

# Patterns indicating a test file references an implementation file.
# Language-agnostic: covers import/require/using/from across ecosystems.
_IMPORT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"""(?:import|from|require)\s*\(?['"](.+?)['"]"""),
    re.compile(r"""using\s+([\w.]+)\s*;"""),
    re.compile(r"""#include\s*[<"](.+?)[>"]"""),
    re.compile(r"""@import\s+['"](.+?)['"]"""),
    re.compile(r"""load\s+['"](.+?)['"]"""),
]

# Patterns that indicate a test is a dummy (zero real assertions)
_DUMMY_TEST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"""expect\s*\(\s*true\s*\)""", re.IGNORECASE),
    re.compile(r"""expect\s*\(\s*1\s*\)\s*\.\s*toBe\s*\(\s*1\s*\)"""),
    re.compile(r"""assert\s+True\s*$""", re.MULTILINE),
    re.compile(r"""assert\s+1\s*==\s*1"""),
    re.compile(r"""Assert\.IsTrue\s*\(\s*true\s*\)""", re.IGNORECASE),
    re.compile(r"""Assert\.AreEqual\s*\(\s*1\s*,\s*1\s*\)""", re.IGNORECASE),
    re.compile(r"""assertEquals\s*\(\s*1\s*,\s*1\s*\)"""),
]


# ------------------------------------------------------------------
# Result
# ------------------------------------------------------------------


@dataclass
class SubmitResult:
    """Outcome of a submit attempt."""

    task_id: str
    is_accepted: bool = False
    phase_results: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    verify_stdout: str = ""
    verify_stderr: str = ""
    verify_exit_code: Optional[int] = None
    consecutive_failures: int = 0

    def summary(self) -> str:
        status = "✅ ACCEPTED" if self.is_accepted else "❌ REJECTED"
        lines = [f"\n{'='*60}", f"  SUBMIT GATE — {self.task_id}: {status}", f"{'='*60}"]
        for phase, result in self.phase_results.items():
            icon = "✅" if result == "PASS" else "❌"
            lines.append(f"  {icon} {phase}: {result}")
        if self.errors:
            lines.append(f"\n  Errors ({len(self.errors)}):")
            for error in self.errors:
                lines.append(f"    • {error}")
        if self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            lines.append(
                f"\n  🚨 CIRCUIT BREAKER: {self.consecutive_failures} consecutive failures."
                "\n     HALT IMEDIATO. Pare de executar código."
                "\n     Transcreva este erro ao Usuário e peça consultoria humana."
                "\n     O Nexus Engine rejeitará ações automáticas nesta task."
            )
        lines.append(f"{'='*60}\n")
        return "\n".join(lines)


# ------------------------------------------------------------------
# Gate
# ------------------------------------------------------------------


class SubmitGate:
    """Evidence-based task completion gate."""

    def __init__(self, project_root: str = ".", plan_name: str = "") -> None:
        self.project_root = Path(project_root).resolve()
        self.plan_name = plan_name
        self.plan_dir = self.project_root / ".nexus" / plan_name
        self.tasks_path = self.plan_dir / "tasks.json"
        self.state_manager = NexusStateManager(project_root)
        self._failure_log_path = self.plan_dir / "submit_failures.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(self, task_id: str) -> SubmitResult:
        """Attempt to transition a task to 'completed'.

        Returns SubmitResult with is_accepted=True only if ALL gates pass:
          1. Task exists and has verify_cmd
          2. Implementation files contain no mock/placeholder code
          3. Test files reference implementation files (anti-dummy)
          4. verify_cmd executes with exit code 0
        """
        result = SubmitResult(task_id=task_id)

        # --- Pre-flight: load task definition ---
        task_def = self._load_task_definition(task_id)
        if task_def is None:
            result.errors.append(f"Task '{task_id}' not found in {self.tasks_path}")
            result.phase_results["Load Task"] = "FAIL"
            return self._finalize(result, accepted=False)
        result.phase_results["Load Task"] = "PASS"

        verify_cmd = task_def.get("verify_cmd", "")
        task_files = task_def.get("files", [])

        if not verify_cmd:
            result.errors.append(
                f"Task '{task_id}' has no verify_cmd defined. "
                "The TaskBreaker must set verify_cmd at task creation time."
            )
            result.phase_results["Verify Command Exists"] = "FAIL"
            return self._finalize(result, accepted=False)
        result.phase_results["Verify Command Exists"] = "PASS"

        # --- Check circuit breaker ---
        result.consecutive_failures = self._load_failure_count(task_id)
        if result.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            result.errors.append(
                f"Circuit breaker active: {result.consecutive_failures} consecutive failures. "
                "Human intervention required."
            )
            result.phase_results["Circuit Breaker"] = "FAIL"
            return self._finalize(result, accepted=False)
        result.phase_results["Circuit Breaker"] = "PASS"

        # --- Phase 1: Anti-Mock Scan on implementation files ---
        mock_result = self._scan_for_mocks(task_files)
        if not mock_result.is_valid:
            result.errors.extend(mock_result.errors)
            result.phase_results["Anti-Mock Scan"] = "FAIL"
            return self._finalize(result, accepted=False)
        result.phase_results["Anti-Mock Scan"] = "PASS"

        # --- Phase 2: Anti-Dummy Test validation ---
        dummy_result = self._validate_test_references(task_files)
        if not dummy_result.is_valid:
            result.errors.extend(dummy_result.errors)
            result.phase_results["Anti-Dummy Test"] = "FAIL"
            return self._finalize(result, accepted=False)
        result.phase_results["Anti-Dummy Test"] = "PASS"

        # --- Phase 3: Execute verify_cmd ---
        exec_result = self._execute_verify_cmd(verify_cmd)
        result.verify_stdout = exec_result["stdout"]
        result.verify_stderr = exec_result["stderr"]
        result.verify_exit_code = exec_result["exit_code"]

        if exec_result["exit_code"] != 0:
            result.errors.append(
                f"verify_cmd failed with exit code {exec_result['exit_code']}.\n"
                f"Command: {verify_cmd}\n"
                f"stderr: {exec_result['stderr'][:500]}"
            )
            result.phase_results["Verify Execution"] = "FAIL"
            return self._finalize(result, accepted=False)
        result.phase_results["Verify Execution"] = "PASS"

        # --- All gates passed: transition state ---
        self.state_manager.update_task_status(task_id, "completed", files=task_files)
        self._reset_failure_count(task_id)

        return self._finalize(result, accepted=True)

    # ------------------------------------------------------------------
    # Phase implementations
    # ------------------------------------------------------------------

    def _load_task_definition(self, task_id: str) -> Optional[dict]:
        """Load a specific task from tasks.json by ID."""
        if not self.tasks_path.exists():
            return None
        with open(self.tasks_path, "r", encoding="utf-8") as fh:
            tasks = json.load(fh)
        for task in tasks:
            if task.get("id") == task_id:
                return task
        return None

    def _scan_for_mocks(self, task_files: list[str]) -> ValidationResult:
        """Scan all task files for mock/placeholder indicators."""
        combined = ValidationResult()
        for filepath in task_files:
            abs_path = self.project_root / filepath
            if not abs_path.exists():
                combined.add_error(f"File not found: {filepath}")
                continue
            content = read_text(abs_path)
            file_result = validate_no_mock_code(content, filepath)
            combined.merge(file_result)
        return combined

    def _validate_test_references(self, task_files: list[str]) -> ValidationResult:
        """Verify that test files actually reference implementation files.

        A test file is identified by common naming conventions across
        languages: *.test.*, *.spec.*, *_test.*, *Test.*, test_*.*.
        If a task has both implementation and test files, the test MUST
        import/reference at least one implementation file from the same task.
        """
        result = ValidationResult()

        impl_files: list[str] = []
        test_files: list[str] = []

        for filepath in task_files:
            if self._is_test_file(filepath):
                test_files.append(filepath)
            else:
                impl_files.append(filepath)

        # If no test files or no impl files, skip this check
        if not test_files or not impl_files:
            return result

        impl_stems = set()
        for impl_path in impl_files:
            stem = Path(impl_path).stem
            impl_stems.add(stem)
            # Also add the filename without extension for cross-language matching
            name_no_ext = Path(impl_path).name.rsplit(".", 1)[0]
            impl_stems.add(name_no_ext)
            # Add parent-relative path for import matching (e.g. "routes/users")
            parts = Path(impl_path).parts
            if len(parts) >= 2:
                impl_stems.add("/".join(parts[-2:]).rsplit(".", 1)[0])

        for test_path in test_files:
            abs_test = self.project_root / test_path
            if not abs_test.exists():
                result.add_error(f"Test file not found: {test_path}")
                continue

            test_content = read_text(abs_test)

            # Check for dummy test patterns (tautological assertions)
            for pattern in _DUMMY_TEST_PATTERNS:
                if pattern.search(test_content):
                    result.add_error(
                        f"Dummy test detected in {test_path}: "
                        f"tautological assertion matching pattern '{pattern.pattern}'. "
                        "Tests must assert real behavior from implementation files."
                    )

            # Check that the test references at least one implementation file
            has_reference = self._test_references_impl(test_content, impl_stems)
            if not has_reference:
                result.add_error(
                    f"Test file '{test_path}' does not reference any implementation file "
                    f"from this task ({', '.join(impl_files)}). "
                    "Tests must import/reference the code they are testing."
                )

        return result

    def _test_references_impl(
        self, test_content: str, impl_stems: set[str]
    ) -> bool:
        """Check if test content references any implementation file stem."""
        # Strategy 1: Check import/require/using patterns
        for pattern in _IMPORT_PATTERNS:
            for match in pattern.finditer(test_content):
                imported_path = match.group(1)
                imported_stem = Path(imported_path).stem
                imported_name = imported_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                if imported_stem in impl_stems or imported_name in impl_stems:
                    return True

        # Strategy 2: Direct text reference to any implementation stem
        for stem in impl_stems:
            if len(stem) > 2 and stem in test_content:
                return True

        return False

    def _execute_verify_cmd(self, verify_cmd: str) -> dict:
        """Execute verify command in a hermetic subprocess."""
        try:
            completed = subprocess.run(
                verify_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=VERIFY_TIMEOUT_SECONDS,
                cwd=str(self.project_root),
            )
            return {
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"TIMEOUT: verify_cmd exceeded {VERIFY_TIMEOUT_SECONDS}s limit.",
            }
        except FileNotFoundError as exc:
            return {
                "exit_code": -2,
                "stdout": "",
                "stderr": f"Command not found: {exc}",
            }

    # ------------------------------------------------------------------
    # Circuit breaker persistence
    # ------------------------------------------------------------------

    def _load_failure_count(self, task_id: str) -> int:
        """Load consecutive failure count for a task."""
        if not self._failure_log_path.exists():
            return 0
        with open(self._failure_log_path, "r", encoding="utf-8") as fh:
            log = json.load(fh)
        return log.get(task_id, {}).get("consecutive_failures", 0)

    def _increment_failure_count(self, task_id: str) -> int:
        """Increment and persist failure count. Returns new count."""
        log: dict = {}
        if self._failure_log_path.exists():
            with open(self._failure_log_path, "r", encoding="utf-8") as fh:
                log = json.load(fh)

        if task_id not in log:
            log[task_id] = {"consecutive_failures": 0, "history": []}

        log[task_id]["consecutive_failures"] += 1
        log[task_id]["history"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "failure",
        })

        self._failure_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._failure_log_path, "w", encoding="utf-8") as fh:
            json.dump(log, fh, indent=2, ensure_ascii=False)

        return log[task_id]["consecutive_failures"]

    def _reset_failure_count(self, task_id: str) -> None:
        """Reset failure count on success."""
        if not self._failure_log_path.exists():
            return
        with open(self._failure_log_path, "r", encoding="utf-8") as fh:
            log = json.load(fh)
        if task_id in log:
            log[task_id]["consecutive_failures"] = 0
            log[task_id]["history"].append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "success_reset",
            })
            with open(self._failure_log_path, "w", encoding="utf-8") as fh:
                json.dump(log, fh, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_test_file(filepath: str) -> bool:
        """Detect test files across languages using naming conventions."""
        name = Path(filepath).name.lower()
        stem = Path(filepath).stem.lower()

        # Pattern-based detection (language-agnostic)
        test_indicators = [
            ".test.", ".spec.", "_test.", "_spec.",
            "test_", "spec_",
        ]
        if any(indicator in name for indicator in test_indicators):
            return True

        # Suffix-based (Java/C# convention: UserTest.java, UserTests.cs)
        if stem.endswith("test") or stem.endswith("tests"):
            return True

        # Directory-based (file inside tests/ or test/ or __tests__/)
        path_lower = filepath.replace("\\", "/").lower()
        test_dirs = ["/tests/", "/test/", "/__tests__/", "/spec/", "/specs/"]
        if any(test_dir in path_lower for test_dir in test_dirs):
            return True

        return False

    def _finalize(self, result: SubmitResult, accepted: bool) -> SubmitResult:
        """Finalize result, update failure count if rejected."""
        result.is_accepted = accepted
        if not accepted:
            result.consecutive_failures = self._increment_failure_count(result.task_id)
        return result


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------


def main() -> None:
    """CLI interface for the Submit Gate."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Nexus Submit Gate — Evidence-based task completion.",
        epilog=(
            "The AI agent MUST use this gate to mark tasks as completed. "
            "Direct manipulation of plan_state.json is PROHIBITED."
        ),
    )
    parser.add_argument("--plan", required=True, help="Plan name (e.g. 'my_plan')")
    parser.add_argument("--task", required=True, help="Task ID (e.g. 'TASK-001')")
    parser.add_argument(
        "--project-root", default=".", help="Project root directory (default: current)"
    )

    args = parser.parse_args()

    gate = SubmitGate(
        project_root=args.project_root,
        plan_name=args.plan,
    )
    result = gate.submit(args.task)
    print(result.summary())

    if not result.is_accepted:
        sys.exit(1)


if __name__ == "__main__":
    main()
