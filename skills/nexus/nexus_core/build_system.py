"""
Nexus Core - Build System Detector

Exposes BuildSystemDetector as an importable alias for BuildSystem,
allowing /review SKILL.md to use: from nexus_core.build_system import BuildSystemDetector

The underlying implementation lives in nexus-dev/scripts/build_system.py
which includes detect_run_command() for start command detection.
"""

from __future__ import annotations

import sys
from pathlib import Path

_nexus_dev_scripts = Path(__file__).resolve().parents[1] / "nexus-dev" / "scripts"
if str(_nexus_dev_scripts) not in sys.path:
    sys.path.insert(0, str(_nexus_dev_scripts))

from build_system import BuildSystem as BuildSystemDetector  # noqa: F401

__all__ = ["BuildSystemDetector"]
