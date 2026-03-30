"""
Nexus Core - Validation Utilities

Validates:
- EARS notation requirements
- Plan document structure
- Task definitions (Atomic Task rule: 1-3 files max)
- Complexity scores (5-dimension model)
"""

import re
from dataclasses import dataclass, field

# ------------------------------------------------------------------
# EARS patterns (case-insensitive multiline matching)
# ------------------------------------------------------------------

_EARS_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\s*-?\s*`?WHEN\s+.+\s+THE SYSTEM SHALL\s+.+`?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*-?\s*`?WHILE\s+.+\s+THE SYSTEM SHALL\s+.+`?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*-?\s*`?IF\s+.+\s+THEN THE SYSTEM SHALL\s+.+`?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*-?\s*`?WHERE\s+.+\s+THE SYSTEM SHALL\s+.+`?\s*$", re.IGNORECASE | re.MULTILINE),
]

COMPLEXITY_DIMENSIONS = {"scope", "integration", "infrastructure", "knowledge", "risk"}

MINIMUM_PLAN_SECTIONS = [
    "## ⚙️ Requisitos Funcionais",
    "## 📋 Tasks",
]

RECOMMENDED_PLAN_SECTIONS = [
    "## 📐 Requisitos Não-Funcionais",
    "## ⚠️ Edge Cases",
    "## 🚧 Constraints",
    "## 📌 Assumptions",
]

MOCK_INDICATORS = [
    "# TODO",
    "# FIXME",
    "pass  # placeholder",
    "raise NotImplementedError",
    "return {}  #",
    "return []  #",
    "return None  # TODO",
    "mock_",
    "_mock(",
]


# ------------------------------------------------------------------
# Result dataclass
# ------------------------------------------------------------------


@dataclass
class ValidationResult:
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.is_valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def merge(self, other: "ValidationResult") -> None:
        """Merge another result into this one."""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        if not other.is_valid:
            self.is_valid = False

    def summary(self) -> str:
        status = "PASS" if self.is_valid else "FAIL"
        parts = [f"[{status}]"]
        if self.errors:
            parts.append(f"{len(self.errors)} error(s): " + "; ".join(self.errors))
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s): " + "; ".join(self.warnings))
        return " | ".join(parts)


# ------------------------------------------------------------------
# EARS validators
# ------------------------------------------------------------------


def is_ears_notation(requirement: str) -> bool:
    """Return True if the requirement line matches any valid EARS pattern."""
    return any(p.match(requirement.strip()) for p in _EARS_PATTERNS)


def validate_ears_block(requirements: list[str]) -> ValidationResult:
    """Validate that every non-empty requirement in a block is valid EARS."""
    result = ValidationResult()
    for i, req in enumerate(requirements, 1):
        stripped = req.strip()
        if not stripped:
            continue
        if not is_ears_notation(stripped):
            result.add_error(
                f"Requirement #{i} is not valid EARS notation: '{stripped[:80]}'"
            )
    return result


# ------------------------------------------------------------------
# Task validators
# ------------------------------------------------------------------


def validate_task_definition(task: dict) -> ValidationResult:
    """
    Validate a single task definition dict.

    Required keys: id, title, files, description
    Atomic Task Rule: max 3 files
    """
    result = ValidationResult()
    required_keys = {"id", "title", "files", "description"}
    missing = required_keys - set(task.keys())
    for key in sorted(missing):
        result.add_error(f"Task missing required field: '{key}'")

    files: list = task.get("files", [])
    if not isinstance(files, list):
        result.add_error(f"Task '{task.get('id', '?')}': 'files' must be a list.")
        return result

    if len(files) > 3:
        result.add_error(
            f"Task '{task.get('id', '?')}' touches {len(files)} files "
            f"(max 3 per Atomic Task Rule). Split this task."
        )
    if len(files) == 0 and task.get("id"):
        result.add_warning(f"Task '{task.get('id')}' has no files defined yet.")

    priority = task.get("priority", "medium")
    if priority not in ("high", "medium", "low"):
        result.add_warning(
            f"Task '{task.get('id', '?')}': unknown priority '{priority}', using 'medium'."
        )

    # Warn if task title doesn't open with an action verb.
    # Titles like "Inicializar X" or "Implementar Y" communicate intent clearly;
    # titles like "Auth layer" or "Fix stuff" degrade executor focus.
    _ACTION_VERBS = {
        "implementar", "criar", "validar", "configurar", "adicionar", "remover",
        "corrigir", "refatorar", "testar", "gerar", "integrar", "definir",
        "construir", "instalar", "inicializar", "registrar", "processar",
        "expor", "serializar", "deserializar", "migrar", "documentar",
        "implement", "create", "validate", "configure", "add", "remove",
        "fix", "refactor", "test", "generate", "integrate", "define",
        "build", "install", "setup", "initialize", "register", "expose",
    }
    title: str = task.get("title", "")
    if title:
        title_words = title.strip().split()
        if title_words:
            first_word = title_words[0].lower().rstrip(":")
            if first_word not in _ACTION_VERBS:
                result.add_warning(
                    f"Task '{task.get('id', '?')}': title '{title[:60]}' doesn't start with an "
                    "action verb (e.g. Implementar, Criar, Validar, Configurar)."
                )

    # Warn if no behavioral acceptance criteria are defined.
    # The Validation Gate handles infra gates (build/tests); acceptance_criteria
    # should capture the specific behavior this task is supposed to prove.
    acceptance_criteria: list = task.get("acceptance_criteria", [])
    if not acceptance_criteria:
        result.add_warning(
            f"Task '{task.get('id', '?')}': acceptance_criteria is empty. "
            "Define at least one observable behavioral criterion "
            "(e.g. 'WHEN X is called THEN it returns Y')."
        )

    return result


def validate_task_list(tasks: list[dict]) -> ValidationResult:
    """Validate all tasks in a list, checking for duplicate IDs."""
    result = ValidationResult()
    seen_ids: set[str] = set()
    for task in tasks:
        sub = validate_task_definition(task)
        result.merge(sub)
        task_id = task.get("id", "")
        if task_id in seen_ids:
            result.add_error(f"Duplicate task ID: '{task_id}'")
        seen_ids.add(task_id)
    return result


# ------------------------------------------------------------------
# Plan validators
# ------------------------------------------------------------------


def validate_plan_structure(plan_content: str) -> ValidationResult:
    """
    Validate that a plan document contains required sections, a minimum of 5 EARS
    requirements (constitutional gate), and at least one entity definition.
    """
    result = ValidationResult()
    for section in MINIMUM_PLAN_SECTIONS:
        if section not in plan_content:
            result.add_error(f"Plan is missing required section: '{section}'")
    for section in RECOMMENDED_PLAN_SECTIONS:
        if section not in plan_content:
            result.add_warning(f"Plan is missing recommended section: '{section}'")
    # Count all EARS requirements (constitutional gate requires >= 5)
    ears_count = sum(len(p.findall(plan_content)) for p in _EARS_PATTERNS)
    if ears_count == 0:
        result.add_error(
            "Plan contains no EARS notation requirements. "
            "Add at least one WHEN/WHILE/IF/WHERE requirement."
        )
    elif ears_count < 5:
        result.add_error(
            f"Plan contains only {ears_count} EARS requirement(s). "
            "Constitutional gate requires a minimum of 5."
        )
    # Check entity dictionary presence (constitutional gate)
    if "rio de Entidades" not in plan_content:
        result.add_error(
            "Plan is missing the Entity Dictionary section ('Dicionario de Entidades'). "
            "At least one domain entity must be defined before generating the spec."
        )
    return result


# ------------------------------------------------------------------
# Complexity score validator
# ------------------------------------------------------------------


def validate_complexity_score(scores: dict[str, int]) -> ValidationResult:
    """
    Validate that all 5 complexity dimensions are present with 1-5 scores.
    Returns result with total and tier classification.
    """
    result = ValidationResult()
    for dim in COMPLEXITY_DIMENSIONS:
        if dim not in scores:
            result.add_error(f"Missing complexity dimension: '{dim}'")
        elif not isinstance(scores[dim], int) or not (1 <= scores[dim] <= 5):
            result.add_error(
                f"Score for '{dim}' must be an integer 1–5, got {scores.get(dim)!r}"
            )
    total = sum(scores.get(d, 0) for d in COMPLEXITY_DIMENSIONS)
    if result.is_valid:
        if total <= 8:
            tier = "SIMPLE"
        elif total <= 15:
            tier = "STANDARD"
        else:
            tier = "COMPLEX"
        result.add_warning(f"Complexity total={total} → tier={tier}")
    return result


def classify_complexity(scores: dict[str, int]) -> str:
    """Return SIMPLE / STANDARD / COMPLEX based on sum of 5-dim scores."""
    total = sum(scores.values())
    if total <= 8:
        return "SIMPLE"
    if total <= 15:
        return "STANDARD"
    return "COMPLEX"


# ------------------------------------------------------------------
# Anti-mock code validator
# ------------------------------------------------------------------


def validate_no_mock_code(source_code: str, filepath: str = "<unknown>") -> ValidationResult:
    """
    Scan source code for known mock/placeholder indicators.
    Returns FAIL if any are found so the AI agent can refuse to commit.
    """
    result = ValidationResult()
    lines = source_code.splitlines()
    for line_no, line in enumerate(lines, 1):
        for indicator in MOCK_INDICATORS:
            if indicator in line:
                result.add_error(
                    f"{filepath}:{line_no} — Mock/placeholder detected: '{indicator}' "
                    "— Replace with a real implementation."
                )
    return result
