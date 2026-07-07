"""Shared helpers: UTF-8 stdout, JSON emission, hashing, safe teardown."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BENCH_VERSION = "0.1.0"


def force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def emit_result(payload: dict, exit_code: int = 0) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.stdout.flush()
    raise SystemExit(exit_code)


def emit_event(kind: str, **fields) -> None:
    if os.environ.get("SKILL_TEST_VERBOSE") == "1" or kind in ("warning", "error"):
        rec = {"event": kind, "ts": now_iso(), **fields}
        sys.stderr.write(json.dumps(rec, ensure_ascii=False) + "\n")
        sys.stderr.flush()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def monotonic() -> float:
    return time.monotonic()


def load_structured(path: Path) -> dict:
    """Load a YAML (or JSON) asset file."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    try:
        import yaml
    except ImportError:
        raise RuntimeError(
            f"PyYAML is required to read {path.name} (pip install pyyaml), "
            "or provide the asset as .json"
        )
    return yaml.safe_load(text)


def dump_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def skill_behavior_hash(skill_dir: Path) -> str:
    """Hash of everything that shapes skill behavior: SKILL.md + references/ + scripts/.

    tests/ and baselines are excluded on purpose: changing the tests must not
    invalidate the seal of the skill itself.
    """
    h = hashlib.sha256()
    paths: list[Path] = []
    top = skill_dir / "SKILL.md"
    if top.exists():
        paths.append(top)
    for sub in ("references", "scripts"):
        base = skill_dir / sub
        if base.is_dir():
            paths.extend(p for p in sorted(base.rglob("*")) if p.is_file() and "__pycache__" not in p.parts)
    for p in sorted(paths):
        h.update(p.relative_to(skill_dir).as_posix().encode())
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:16]


def _on_rm_error(func, path, exc_info):  # pragma: no cover - windows quirk
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def safe_rmtree(path: Path) -> None:
    """rm -rf that survives read-only files inside .git on Windows."""
    if path.exists():
        shutil.rmtree(path, onexc=_on_rm_error)


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def estimate_tokens(text: str) -> int:
    """Crude estimate (chars/4). Only ever reported as 'estimated'."""
    return max(0, round(len(text) / 4))
