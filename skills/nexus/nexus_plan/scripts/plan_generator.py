"""
Nexus Plan - Plan Generator

Assembles the final spec.md document from:
  - ComplexityAssessment (from prompt_expander)
  - Resolved decisions (from option_resolver)
  - EARS requirements collected during discovery
  - Task sketches (later refined by task_breaker)

The generated plan is written to:
  .nexus/{plan_name}/spec.md

Usage:
    generator = PlanGenerator(plan_name="auth-system", project_root=".")
    generator.add_ears_requirement("WHEN user submits login form THE SYSTEM SHALL validate credentials")
    generator.add_task_sketch("Implement JWT authentication layer", files=["src/auth.py", "src/middleware.py"])
    path = generator.generate(assessment, resolver)
    print(f"Plan written to {path}")
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus_core.file_utils import ensure_dir, write_text
from nexus_core.validation import validate_plan_structure, validate_ears_block


# ------------------------------------------------------------------
# Data models
# ------------------------------------------------------------------


@dataclass
class EarsRequirement:
    notation: str  # The full EARS string
    category: str = "Functional"  # Functional | Non-Functional | Security | etc.


@dataclass
class EntityEntry:
    name: str
    definition: str
    entity_type: str = "Domain"  # Domain | Actor | External | Value Object


@dataclass
class TaskSketch:
    title: str
    description: str
    files: list[str] = field(default_factory=list)
    priority: str = "medium"  # high | medium | low
    dependencies: list[str] = field(default_factory=list)


@dataclass
class ActorEntry:
    name: str
    actor_type: str = "Primary"  # Primary | Secondary | External
    responsibility: str = ""


@dataclass
class UseCaseEntry:
    use_case: str
    actors: str
    description: str = ""


@dataclass
class UCDrilldown:
    nome: str
    ator: str = ""
    descricao: str = ""
    pre_condicoes: list[str] = field(default_factory=list)
    fluxo: list[str] = field(default_factory=list)
    pos_condicoes: list[str] = field(default_factory=list)
    entidades: list = field(default_factory=list)


# ------------------------------------------------------------------
# Generator
# ------------------------------------------------------------------


class PlanGenerator:
    """Generates a spec-driven plan markdown document."""

    def __init__(self, plan_name: str, project_root: str = ".") -> None:
        self.plan_name = plan_name
        self.project_root = Path(project_root).resolve()
        self._requirements: list[EarsRequirement] = []
        self._entities: list[EntityEntry] = []
        self._invariants: list[str] = []
        self._component_diagram: str = ""
        self._nfrs: list[str] = []
        self._constraints: list[str] = []
        self._assumptions: list[str] = []
        self._edge_cases: list[str] = []
        self._task_sketches: list[TaskSketch] = []
        self._acceptance_criteria: list[str] = []
        self._state_diagrams: list[tuple[str, str]] = []
        self._use_case_diagram: str = ""
        self._actor_dictionary: list[ActorEntry] = []
        self._use_case_matrix: list[UseCaseEntry] = []
        self._uc_drilldowns: list[UCDrilldown] = []

    # ------------------------------------------------------------------
    # Builder methods
    # ------------------------------------------------------------------

    def add_ears_requirement(self, notation: str, category: str = "Functional") -> None:
        self._requirements.append(EarsRequirement(notation=notation.strip(), category=category))

    def add_entity(
        self,
        name: str,
        definition: str,
        entity_type: str = "Domain",
    ) -> None:
        self._entities.append(
            EntityEntry(name=name.strip(), definition=definition.strip(), entity_type=entity_type)
        )

    def add_invariant(self, invariant: str) -> None:
        self._invariants.append(invariant.strip())

    def set_component_diagram(self, mermaid: str) -> None:
        """Set the C4 component diagram (Mermaid flowchart TD with layer subgraphs)."""
        self._component_diagram = mermaid.strip()

    def add_nfr(self, nfr: str) -> None:
        self._nfrs.append(nfr.strip())

    def add_constraint(self, constraint: str) -> None:
        self._constraints.append(constraint.strip())

    def add_assumption(self, assumption: str) -> None:
        self._assumptions.append(assumption.strip())

    def add_edge_case(self, edge_case: str) -> None:
        self._edge_cases.append(edge_case.strip())

    def add_task_sketch(
        self,
        title: str,
        description: str = "",
        files: Optional[list[str]] = None,
        priority: str = "medium",
        dependencies: Optional[list[str]] = None,
    ) -> None:
        self._task_sketches.append(
            TaskSketch(
                title=title,
                description=description,
                files=files or [],
                priority=priority,
                dependencies=dependencies or [],
            )
        )

    def add_acceptance_criterion(self, criterion: str) -> None:
        self._acceptance_criteria.append(criterion.strip())

    def add_state_diagram(self, entity_name: str, mermaid: str) -> None:
        """Add a state machine diagram (Mermaid stateDiagram) for a stateful entity."""
        self._state_diagrams.append((entity_name.strip(), mermaid.strip()))

    # ------------------------------------------------------------------
    # UML Functional Standard (required by constitutional gate)
    # ------------------------------------------------------------------

    def add_use_case_diagram(self, mermaid: str) -> None:
        """Set the Use Case diagram (Mermaid graph LR, actors as circles with emojis)."""
        self._use_case_diagram = mermaid.strip()

    def add_actor_dictionary(self, actors: list[ActorEntry]) -> None:
        """Set actor dictionary entries."""
        self._actor_dictionary = list(actors)

    def add_use_case_matrix(self, matrix: list[UseCaseEntry]) -> None:
        """Set use case matrix entries."""
        self._use_case_matrix = list(matrix)

    def add_uc_drilldown(self, drilldown: UCDrilldown) -> None:
        """Add a use-case drilldown entry."""
        self._uc_drilldowns.append(drilldown)

    # ------------------------------------------------------------------
    # Core generation
    # ------------------------------------------------------------------

    def generate(
        self,
        assessment: object = None,
        resolver: object = None,
        raw_prompt: str = "",
    ) -> Path:
        """Render the plan markdown and write it to disk. Returns the path."""
        content = self._render(assessment, resolver, raw_prompt)
        validation = validate_plan_structure(content)
        if not validation.is_valid:
            raise ValueError(
                f"Generated plan failed validation:\n" + "\n".join(validation.errors)
            )
        specs_dir = self.project_root / ".nexus" / self.plan_name
        ensure_dir(specs_dir)
        plan_path = specs_dir / "spec.md"
        write_text(plan_path, content)
        return plan_path

    def _render(self, assessment: object, resolver: object, raw_prompt: str) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines: list[str] = []

        # Header
        lines += [
            f"# 📋 Plan: {self.plan_name}",
            f"\n**Generated:** {now}  ",
            f"**Framework:** Nexus v2 (spec-driven)  ",
            f"**Status:** `READY_FOR_DEV`",
            "",
        ]

        if raw_prompt:
            lines += [f"> **Original Request:** _{raw_prompt}_\n"]

        # Complexity
        if assessment is not None:
            lines += [assessment.to_markdown(), ""]

        # Decisions
        if resolver is not None:
            lines += [resolver.to_markdown(), ""]

        # Entity Dictionary
        if self._entities:
            lines += ["---", "", "## 🗂️ Dicionário de Entidades\n"]
            lines.append("> Vocabulário canônico do domínio — toda task e requisito usa estas definições.")
            lines.append("")
            lines.append("| Entidade | Tipo | Definição |")
            lines.append("|----------|------|-----------|")
            for e in self._entities:
                lines.append(f"| **{e.name}** | `{e.entity_type}` | {e.definition} |")
            lines.append("")

        # C4 Component Diagram
        if self._component_diagram:
            lines += ["---", "", "## 🏛️ Mapa de Componentes\n"]
            lines.append("> Visão C4 das camadas e fronteiras do sistema.")
            lines.append("")
            lines.append("```mermaid")
            lines.append(self._component_diagram)
            lines.append("```")
            lines.append("")

        # UML Functional Standard (Casos de Uso — constitutional gate)
        if self._use_case_diagram or self._actor_dictionary or self._use_case_matrix or self._uc_drilldowns:
            lines += ["---", "", "## 🎭 Casos de Uso\n"]
            if self._use_case_diagram:
                lines += ["### 5.1 Diagrama de Casos de Uso\n", "```mermaid", self._use_case_diagram, "```", ""]
            if self._actor_dictionary:
                lines += ["### 5.2 Dicionário de Atores\n"]
                lines.append("| Ator | Tipo | Responsabilidade |")
                lines.append("|------|------|-----------------|")
                for actor in self._actor_dictionary:
                    lines.append(f"| {actor.name} | {actor.actor_type} | {actor.responsibility} |")
                lines.append("")
            if self._use_case_matrix:
                lines += ["### 5.3 Matriz de Casos de Uso\n"]
                lines.append("| UC | Descrição | Ator(es) |")
                lines.append("|----|-----------|---------|")
                for uc in self._use_case_matrix:
                    lines.append(f"| {uc.use_case} | {uc.description} | {uc.actors} |")
                lines.append("")
            for drill_idx, drilldown in enumerate(self._uc_drilldowns, 1):
                lines += [f"### 5.{3 + drill_idx} Drill-down: {drilldown.nome}\n"]
                if drilldown.ator:
                    lines.append(f"**Ator:** {drilldown.ator}\n")
                if drilldown.descricao:
                    lines.append(f"**Descrição:** {drilldown.descricao}\n")
                if drilldown.pre_condicoes:
                    lines += ["**Pré-Condições:**"] + [f"- {pc}" for pc in drilldown.pre_condicoes] + [""]
                if drilldown.fluxo:
                    lines.append("**Fluxo:**")
                    for step_num, step in enumerate(drilldown.fluxo, 1):
                        lines.append(f"{step_num}. {step}")
                    lines.append("")
                if drilldown.pos_condicoes:
                    lines += ["**Pós-Condições:**"] + [f"- {pc}" for pc in drilldown.pos_condicoes] + [""]
                if drilldown.entidades:
                    lines += ["**Micro-Dicionário de Entidades:**", "| Entidade | Tipo | Definição |", "|----------|------|-----------|"]
                    for ent in drilldown.entidades:
                        lines.append(f"| {ent.get('name', '')} | {ent.get('type', '')} | {ent.get('definition', '')} |")
                lines.append("")

        # Functional Requirements
        functional = [r for r in self._requirements if r.category == "Functional"]
        if functional:
            lines += ["---", "", "## ⚙️ Requisitos Funcionais\n"]
            for req in functional:
                lines.append(f"- `{req.notation}`")
            lines.append("")

        # System Invariants (always-true rules, structurally distinct from event-driven EARS)
        if self._invariants:
            lines += ["## 🧱 Invariantes do Sistema\n"]
            lines.append("> Regras que o sistema **sempre** respeita, independente de evento ou contexto.")
            lines.append("")
            for inv in self._invariants:
                lines.append(f"- {inv}")
            lines.append("")

        # State Diagrams for stateful entities
        if self._state_diagrams:
            lines += ["## 🔄 Ciclo de Vida das Entidades\n"]
            lines.append("> Máquinas de estado para entidades com ciclo de vida complexo.")
            lines.append("")
            for entity_name, mermaid in self._state_diagrams:
                lines.append(f"### {entity_name}\n")
                lines.append("```mermaid")
                lines.append(mermaid)
                lines.append("```")
                lines.append("")

        # Non-functional requirements
        if self._nfrs:
            lines += ["## 📐 Requisitos Não-Funcionais\n"]
            for nfr in self._nfrs:
                lines.append(f"- {nfr}")
            lines.append("")

        # Security / other categories
        other_cats = {r.category for r in self._requirements if r.category != "Functional"}
        for cat in sorted(other_cats):
            reqs = [r for r in self._requirements if r.category == cat]
            lines += [f"## {cat} Requirements\n"]
            for req in reqs:
                lines.append(f"- `{req.notation}`")
            lines.append("")

        # Constraints
        if self._constraints:
            lines += ["## 🚧 Constraints\n"]
            for c in self._constraints:
                lines.append(f"- {c}")
            lines.append("")

        # Assumptions
        if self._assumptions:
            lines += ["## 📌 Assumptions\n"]
            for a in self._assumptions:
                lines.append(f"- {a}")
            lines.append("")

        # Edge Cases
        if self._edge_cases:
            lines += ["## ⚠️ Edge Cases\n"]
            for e in self._edge_cases:
                lines.append(f"- {e}")
            lines.append("")

        # Acceptance Criteria
        if self._acceptance_criteria:
            lines += ["## ✅ Acceptance Criteria\n"]
            for ac in self._acceptance_criteria:
                lines.append(f"- {ac}")
            lines.append("")

        # Tasks
        lines += ["---", "", "## 📋 Tasks\n"]
        if self._task_sketches:
            lines.append("| ID | Title | Files | Priority |")
            lines.append("|----|-------|-------|----------|")
            for i, task in enumerate(self._task_sketches, 1):
                task_id = f"task-{i:03d}"
                files_str = ", ".join(f"`{f}`" for f in task.files) if task.files else "_TBD_"
                lines.append(f"| {task_id} | {task.title} | {files_str} | {task.priority} |")
            lines.append("")
            for i, task in enumerate(self._task_sketches, 1):
                task_id = f"task-{i:03d}"
                lines += [
                    f"### {task_id}: {task.title}\n",
                    f"**Description:** {task.description or 'See requirements above.'}\n",
                ]
                if task.files:
                    lines.append(f"**Files:** {', '.join(task.files)}")
                if task.dependencies:
                    lines.append(f"**Depends on:** {', '.join(task.dependencies)}")
                lines.append(f"**Priority:** {task.priority}\n")
        else:
            lines.append(
                "_Tasks will be generated by `/dev` task_breaker from the requirements above._"
            )
        lines.append("")

        # Footer mandate
        lines += [
            "---",
            "",
            "## 🔒 Execution Mandate",
            "",
            "> **`COMPLETE_ALL_TASKS_NO_EXCEPTIONS`** — This plan must be executed in full.",
            "> No mocks, no placeholders, no simplified implementations.",
            "> Every EARS requirement must have a passing test.",
            "> Run `/dev` to start execution.",
        ]

        return "\n".join(lines)

