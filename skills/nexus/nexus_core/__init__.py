"""
Nexus Core - Shared utilities for the Nexus Framework.

Provides:
- StateManager: Persistent .nexus/plan_state.json management
- FileUtils: Common file operations
- Validation: EARS notation and plan/task structure validators
- SubmitGate: Evidence-based task completion gate
"""

from .state_manager import NexusStateManager
from .file_utils import ensure_dir, read_text, write_text, sha256_text, copy_template
from .validation import (
    ValidationResult,
    validate_ears_block,
    validate_task_definition,
    validate_task_list,
    validate_plan_structure,
    validate_complexity_score,
    validate_no_mock_code,
    is_ears_notation,
    classify_complexity,
)
from .submit_gate import SubmitGate, SubmitResult

__all__ = [
    "NexusStateManager",
    "SubmitGate",
    "SubmitResult",
    "ensure_dir",
    "read_text",
    "write_text",
    "sha256_text",
    "copy_template",
    "ValidationResult",
    "validate_ears_block",
    "validate_task_definition",
    "validate_task_list",
    "validate_plan_structure",
    "validate_complexity_score",
    "validate_no_mock_code",
    "is_ears_notation",
    "classify_complexity",
]
