"""
Nexus Dev - Code Generator Helpers

NOT a code generation engine (that is the AI agent's job).
Instead, this module provides:

1. Anti-mock validator  — scans generated code for forbidden patterns
2. Implementation completeness checker — verifies all required code elements exist
3. Dependency verifier  — checks that imported libraries are in requirements.txt / package.json
4. Commit message builder — creates Conventional Commits messages for task micro-commits

Usage:
    checker = CodeQualityChecker(project_root=".")
    result = checker.validate_file("src/auth.py")
    if not result.is_valid:
        for err in result.errors:
            print(err)

    msg = CommitMessageBuilder.build("task-003", "feat", "auth", "Add JWT validation middleware")
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Optional

def _find_nexus_core_root() -> Path:
    """Walk up from this file until we find the directory containing nexus_core."""
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "nexus_core").is_dir():
            return candidate
    raise RuntimeError(
        "nexus_core package not found in any parent directory of "
        f"{here}. Ensure nexus_core/ is installed alongside this skill."
    )


sys.path.insert(0, str(_find_nexus_core_root()))

from nexus_core.file_utils import read_text
from nexus_core.validation import ValidationResult, validate_no_mock_code


# ------------------------------------------------------------------
# Anti-mock patterns (beyond basic ones in validation.py)
# ------------------------------------------------------------------

_EXTENDED_MOCK_PATTERNS = [
    (r"#\s*TODO", "TODO comment — remove before committing"),
    (r"#\s*FIXME", "FIXME comment — resolve before committing"),
    (r"#\s*HACK", "HACK comment — refactor before committing"),
    (r"pass\s*$", "Bare `pass` in function body — implement it"),
    (r"raise\s+NotImplementedError", "NotImplementedError — implement the method"),
    (r'return\s+\{\s*\}\s*$', "Empty dict return — implement real logic"),
    (r'return\s+\[\s*\]\s*$', "Empty list return — implement real logic"),
    (r'return\s+None\s*#\s*TODO', "None return with TODO — implement it"),
    (r'"mock|placeholder|fake|dummy"', "Suspicious string literal suggesting mock data"),
]

_EXTENDED_MOCK_RE = [(re.compile(p, re.IGNORECASE), msg) for p, msg in _EXTENDED_MOCK_PATTERNS]


# ------------------------------------------------------------------
# Code Quality Checker
# ------------------------------------------------------------------


class CodeQualityChecker:
    """Validates implementation quality for Nexus anti-mock enforcement."""

    def __init__(self, project_root: str = ".") -> None:
        self.project_root = Path(project_root).resolve()

    def validate_file(self, filepath: "str | Path") -> ValidationResult:
        """Full validation of a single source file."""
        p = Path(filepath)
        if not p.exists():
            result = ValidationResult()
            result.add_error(f"File not found: {filepath}")
            return result

        source = read_text(p)
        result = validate_no_mock_code(source, str(p))

        # Extended pattern check
        lines = source.splitlines()
        for line_no, line in enumerate(lines, 1):
            for pattern, msg in _EXTENDED_MOCK_RE:
                if pattern.search(line.strip()):
                    result.add_error(f"{p}:{line_no} — {msg}: `{line.strip()[:60]}`")

        # Python-specific AST checks
        if p.suffix == ".py":
            result.merge(self._validate_python_ast(source, str(p)))

        return result

    def _validate_python_ast(self, source: str, filepath: str) -> ValidationResult:
        result = ValidationResult()
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            result.add_error(f"{filepath}: Syntax error — {exc}")
            return result

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check for functions with only `pass` or `...` in body
                has_only_pass = all(isinstance(n, ast.Pass) for n in node.body)
                has_only_ellipsis = all(
                    isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant)
                    and getattr(n.value, "value", None) is ...
                    for n in node.body
                )
                if (has_only_pass or has_only_ellipsis) and not node.name.startswith("_abstract"):
                    result.add_error(
                        f"{filepath}:{node.lineno} — Function `{node.name}` has empty body. "
                        "Implement it or prefix with `_abstract_` if intentionally abstract."
                    )
        return result

    def validate_project(self, extensions: list[str] = None) -> ValidationResult:
        """Validate all source files in the project."""
        if extensions is None:
            extensions = [".py", ".ts", ".js"]
        combined = ValidationResult()
        for ext in extensions:
            for filepath in self.project_root.rglob(f"*{ext}"):
                parts = filepath.relative_to(self.project_root).parts
                if any(p in (".venv", "venv", "node_modules", "__pycache__", ".temp") for p in parts):
                    continue
                sub = self.validate_file(filepath)
                combined.merge(sub)
        return combined


# ------------------------------------------------------------------
# Dependency Verifier
# ------------------------------------------------------------------


class DependencyVerifier:
    """Checks that imports in source files are declared in the project manifest."""

    def __init__(self, project_root: str = ".") -> None:
        self.project_root = Path(project_root).resolve()

    def get_declared_packages(self) -> set[str]:
        """Return all declared dependency names (lowercase)."""
        declared: set[str] = set()
        req_files = [
            "requirements.txt",
            "requirements-dev.txt",
            "pyproject.toml",
            "package.json",
        ]
        for rel_path in req_files:
            full_path = self.project_root / rel_path
            if not full_path.exists():
                continue
            if full_path.suffix == ".txt":
                for line in read_text(full_path).splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        pkg = re.split(r"[>=<!;]", line)[0].strip().lower().replace("-", "_")
                        declared.add(pkg)
            elif full_path.name == "package.json":
                pkg_json = json.loads(read_text(full_path))
                for name in {**pkg_json.get("dependencies", {}), **pkg_json.get("devDependencies", {})}:
                    declared.add(name.lower())
        return declared

    def check_python_imports(self, filepath: "str | Path") -> ValidationResult:
        """Check that third-party imports in a Python file are declared."""
        result = ValidationResult()
        if hasattr(sys, "stdlib_module_names"):
            stdlib_modules: set[str] = sys.stdlib_module_names  # type: ignore[attr-defined]
        else:
            # Fallback for Python < 3.10: cover the most common stdlib top-level names.
            # importlib.util.find_spec is not used here to avoid the cost of repeated
            # subprocess/spec resolution; the set errs on the side of missing entries
            # producing warnings rather than blocking the build.
            stdlib_modules = {
                "abc", "ast", "asyncio", "base64", "builtins", "collections",
                "concurrent", "contextlib", "copy", "csv", "dataclasses", "datetime",
                "decimal", "enum", "functools", "gc", "glob", "gzip", "hashlib",
                "hmac", "html", "http", "importlib", "inspect", "io", "itertools",
                "json", "logging", "math", "multiprocessing", "operator", "os",
                "pathlib", "pickle", "platform", "pprint", "queue", "random", "re",
                "shutil", "signal", "socket", "sqlite3", "ssl", "stat", "string",
                "struct", "subprocess", "sys", "tempfile", "textwrap", "threading",
                "time", "timeit", "traceback", "types", "typing", "unittest",
                "urllib", "uuid", "warnings", "weakref", "xml", "zipfile",
            }
        declared = self.get_declared_packages()
        try:
            tree = ast.parse(read_text(filepath))
        except (SyntaxError, OSError):
            return result

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    pkg = alias.name.split(".")[0].lower()
                    if pkg not in stdlib_modules and pkg not in declared:
                        result.add_warning(
                            f"{filepath}: Import `{pkg}` not found in requirements.txt. "
                            "Add it or it may fail in CI."
                        )
            elif isinstance(node, ast.ImportFrom) and node.module:
                pkg = node.module.split(".")[0].lower()
                if pkg not in stdlib_modules and pkg not in declared:
                    result.add_warning(
                        f"{filepath}: `from {pkg}` not found in requirements.txt."
                    )
        return result


# ------------------------------------------------------------------
# Commit Message Builder
# ------------------------------------------------------------------


class CommitMessageBuilder:
    """Builds Conventional Commits messages for Nexus micro-commits."""

    VALID_TYPES = {
        "feat", "fix", "refactor", "test", "docs", "chore", "build", "ci", "perf", "style",
    }

    @classmethod
    def build(
        cls,
        task_id: str,
        commit_type: str,
        scope: str,
        description: str,
    ) -> str:
        """
        Build a Conventional Commit message for a completed Nexus task.

        Format: type(scope): description
        (Conventional Commits pure — no [Task-XXX] prefix)
        """
        if commit_type not in cls.VALID_TYPES:
            commit_type = "feat"
        scope_part = f"({scope})" if scope else ""
        msg = f"{commit_type}{scope_part}: {description}"
        if len(msg) > 100:
            msg = msg[:97] + "..."
        return msg

    @classmethod
    def build_from_task(cls, task: object, commit_type: str = "feat") -> str:
        """Build message from an AtomicTask or QueueItem object."""
        scope = ""
        if hasattr(task, "files") and task.files:
            first_file = Path(task.files[0])
            scope = first_file.parent.name or first_file.stem
        return cls.build(
            task_id=task.id,
            commit_type=commit_type,
            scope=scope,
            description=task.title,
        )
