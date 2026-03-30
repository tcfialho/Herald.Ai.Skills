"""
Nexus Dev - Build System

Detects and runs the project's build/compile step.
Captures structured pass/fail output for use in /review validation.

Supported build systems (auto-detected):
  - Python    : import check via py_compile
  - TypeScript: tsc --noEmit
  - Node.js   : npm run build
  - Go        : go build ./...
  - .NET      : dotnet build
  - Rust       : cargo build
  - Docker    : docker build

Usage:
    bs = BuildSystem(project_root=".")
    result = bs.run()
    if not result.passed:
        print(result.error_summary)
    bs.save_result(".temp/build_result.json")
"""

from __future__ import annotations

import json
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
class BuildResult:
    build_system: str
    passed: bool
    duration_seconds: float = 0.0
    raw_output: str = ""
    error_summary: str = ""
    warnings_count: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def summary(self) -> str:
        status = "SUCCESS" if self.passed else "FAILURE"
        warn = f" ({self.warnings_count} warnings)" if self.warnings_count else ""
        return f"[BUILD {status}] {self.build_system}{warn} in {self.duration_seconds:.2f}s"

    def to_markdown(self) -> str:
        emoji = "✅" if self.passed else "❌"
        lines = [
            f"### {emoji} Build Result ({self.build_system})\n",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Status | {'SUCCESS' if self.passed else 'FAILURE'} |",
            f"| Duration | {self.duration_seconds:.2f}s |",
            f"| Warnings | {self.warnings_count} |",
        ]
        if self.error_summary:
            lines += ["", f"**Build Errors:**\n```\n{self.error_summary[:2000]}\n```"]
        return "\n".join(lines)


# ------------------------------------------------------------------
# Build System
# ------------------------------------------------------------------


class BuildSystem:
    def __init__(self, project_root: str = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self._last_result: Optional[BuildResult] = None

    # ------------------------------------------------------------------
    # Auto-detection
    # ------------------------------------------------------------------

    def detect_build_system(self) -> str:
        root = self.project_root
        if (root / "tsconfig.json").exists():
            return "typescript"
        if (root / "package.json").exists():
            with open(root / "package.json", encoding="utf-8") as fh:
                pkg = json.load(fh)
            if "build" in pkg.get("scripts", {}):
                return "npm"
        if (root / "go.mod").exists():
            return "go"
        if any(root.glob("**/*.csproj")):
            return "dotnet"
        if (root / "Cargo.toml").exists():
            return "cargo"
        if (root / "Dockerfile").exists():
            return "docker"
        if list(root.rglob("*.py")):
            return "python"
        return "unknown"

    def detect_run_command(self) -> str:
        """Detect the command to run/start the project after a successful build.
        Returns a ready-to-use shell command string.
        """
        root = self.project_root
        build_type = self.detect_build_system()
        if build_type in ("typescript", "npm"):
            pkg_path = root / "package.json"
            if pkg_path.exists():
                with open(pkg_path, encoding="utf-8") as fh:
                    pkg = json.load(fh)
                scripts = pkg.get("scripts", {})
                for candidate in ("dev", "start", "serve"):
                    if candidate in scripts:
                        return f"npm run {candidate}"
            return "npm start"
        if build_type == "python":
            for entry in ("src/main.py", "src/app.py", "main.py", "app.py"):
                entry_path = root / entry
                if entry_path.exists():
                    content = entry_path.read_text(encoding="utf-8", errors="ignore")
                    if "FastAPI" in content or "uvicorn" in content:
                        module = entry.replace("/", ".").replace(".py", "")
                        return f"uvicorn {module}:app --reload"
                    if "Flask" in content or "flask.Flask" in content:
                        return "flask run"
                    return f"python {entry}"
            if (root / "pyproject.toml").exists():
                return "python -m <module>"
            return "python src/main.py"
        run_commands = {
            "go": "go run ./...",
            "dotnet": "dotnet run",
            "cargo": "cargo run",
        }
        return run_commands.get(build_type, f"# Run command unknown for build type: {build_type}")

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(
        self, build_system: Optional[str] = None, extra_args: list[str] = None
    ) -> BuildResult:
        resolved = build_system or self.detect_build_system()
        command = self._build_command(resolved, extra_args or [])
        if not command:
            return BuildResult(
                build_system=resolved,
                passed=False,
                error_summary=f"No supported build command for '{resolved}'.",
            )

        start = time.perf_counter()
        try:
            if resolved == "python":
                return self._run_python_compile()
            proc = subprocess.run(
                command,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=600,
            )
        except subprocess.TimeoutExpired:
            return BuildResult(
                build_system=resolved,
                passed=False,
                error_summary="Build timed out after 600 seconds.",
            )
        duration = time.perf_counter() - start
        raw = proc.stdout + "\n" + proc.stderr
        result = BuildResult(
            build_system=resolved,
            passed=proc.returncode == 0,
            duration_seconds=duration,
            raw_output=raw[:5000],
            warnings_count=raw.lower().count("warning"),
        )
        if not result.passed:
            error_lines = [l for l in raw.splitlines() if "error" in l.lower()][:30]
            result.error_summary = "\n".join(error_lines)
        self._last_result = result
        return result

    def _build_command(self, build_system: str, extra_args: list[str]) -> list[str]:
        commands = {
            "typescript": ["npx", "tsc", "--noEmit"],
            "npm": ["npm", "run", "build"],
            "go": ["go", "build", "./..."],
            "dotnet": ["dotnet", "build", "--no-restore"],
            "cargo": ["cargo", "build"],
            "docker": ["docker", "build", "-t", "nexus_build_check", "."],
        }
        base = commands.get(build_system)
        if base is None:
            return []
        return base + extra_args

    def _run_python_compile(self) -> BuildResult:
        """Compile all .py files — py_compile for errors, subprocess for warning count."""
        import py_compile
        start = time.perf_counter()
        errors: list[str] = []
        checked_files: list[Path] = []
        for py_file in sorted(self.project_root.rglob("*.py")):
            relative = py_file.relative_to(self.project_root)
            # Skip virtual envs and caches
            parts = relative.parts
            if any(p in (".venv", "venv", "env", "__pycache__", ".temp") for p in parts):
                continue
            checked_files.append(py_file)
            try:
                py_compile.compile(str(py_file), doraise=True)
            except py_compile.PyCompileError as exc:
                errors.append(str(exc))
            except OSError as exc:
                errors.append(f"{py_file}: OSError — {exc}")

        # Count warnings by running Python with -W all via subprocess.
        # py_compile alone never emits warning lines; subprocess captures them.
        warnings_count = 0
        if checked_files:
            try:
                warn_proc = subprocess.run(
                    ["python", "-W", "all", "-m", "compileall", "-q", "."],
                    cwd=str(self.project_root),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                warn_output = warn_proc.stdout + warn_proc.stderr
                warnings_count = warn_output.lower().count("warning")
            except (subprocess.TimeoutExpired, OSError):
                pass

        duration = time.perf_counter() - start
        error_summary = "\n".join(errors[:20])
        result = BuildResult(
            build_system="python",
            passed=len(errors) == 0,
            duration_seconds=duration,
            raw_output=error_summary,
            error_summary=error_summary,
            warnings_count=warnings_count,
        )
        self._last_result = result
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
    def last_result(self) -> Optional[BuildResult]:
        return self._last_result


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    bs = BuildSystem(project_root=root)
    result = bs.run()
    print(result.summary)
    out_path = Path(root) / ".temp" / "build_result.json"
    bs.save_result(out_path)
    print(f"Build result written to {out_path}")
    sys.exit(0 if result.passed else 1)
