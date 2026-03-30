"""
nexus_review — Python package for the Nexus /review stage.

Scripts live in nexus_review/scripts/ and are loaded here for clean
top-level imports:

    from nexus_review import TestExecutor, ComplianceChecker
    from nexus_review import QualityGates, HomologationEvidence
    from nexus_review import CertificationEngine
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent / "scripts"


def _load(module_name: str):
    """Load a module from nexus_review/scripts/ and register it in sys.modules."""
    full_key = f"nexus_review.{module_name}"
    if full_key in sys.modules:
        return sys.modules[full_key]
    path = _scripts_dir / f"{module_name}.py"
    if not path.exists():
        raise ImportError(
            f"Cannot load nexus_review module '{module_name}': file not found at {path}"
        )
    spec = importlib.util.spec_from_file_location(full_key, path)
    if spec is None or spec.loader is None:
        raise ImportError(
            f"Cannot create import spec for nexus_review module '{module_name}' at {path}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_key] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(full_key, None)
        raise ImportError(
            f"Failed to load nexus_review module '{module_name}': {exc}"
        ) from exc
    return module


_test_executor = _load("test_executor")
_compliance_checker = _load("compliance_checker")
_quality_gates = _load("quality_gates")
_certification_engine = _load("certification_engine")

TestExecutor = _test_executor.TestExecutor
HomologationTestEvidence = _test_executor.HomologationTestEvidence
HomologationEvidence = _quality_gates.HomologationEvidence
ComplianceChecker = _compliance_checker.ComplianceChecker
QualityGates = _quality_gates.QualityGates
CertificationEngine = _certification_engine.CertificationEngine

__all__ = [
    "TestExecutor",
    "HomologationTestEvidence",
    "HomologationEvidence",
    "ComplianceChecker",
    "QualityGates",
    "CertificationEngine",
]
