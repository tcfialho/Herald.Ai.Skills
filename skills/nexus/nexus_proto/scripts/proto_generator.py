"""
Nexus Proto - Proto Generator

Manages the A/B wireframe decision loop for a given plan:
  - Extracts screen candidates from spec.md
  - Tracks per-screen state (pending / iterating / decided)
  - Records chosen variant, dimension in dispute, and change request history
  - Serialises all decisions to proto.json
  - Generates wireframes.md summary

Usage:
    generator = ProtoGenerator(plan_name="todo-app", spec_path=".nexus/todo-app/spec.md")
    screens = generator.extract_screens()
    generator.record_decision(
        screen_id="S01",
        screen_name="Lista de Tarefas",
        dimension="posição dos filtros",
        variant_a_intent="filtros → contexto primeiro",
        variant_b_intent="input → ação imediata",
        chosen="A",
        change_requests=["pills menores"],
        svg_final="<svg>...</svg>",
    )
    generator.save(".nexus/todo-app/proto.json")
    generator.export_wireframes_md(".nexus/todo-app/wireframes.md")
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional


ScreenStatus = Literal["pending", "iterating", "decided", "blocked"]
ChosenVariant = Literal["A", "B"]

MAX_ITERATIONS_PER_SCREEN = 5


# ------------------------------------------------------------------
# Data models
# ------------------------------------------------------------------


@dataclass
class ChangeRequest:
    iteration: int
    description: str
    base_variant: str  # "A" or "B" — which variant was modified
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ScreenDecision:
    screen_id: str                  # e.g. "S01"
    screen_name: str                # e.g. "Lista de Tarefas"
    source_ucs: list[str]           # e.g. ["UC01", "UC03"]
    dimension: str                  # the single disputed dimension
    variant_a_intent: str           # annotation: why A
    variant_b_intent: str           # annotation: why B
    status: ScreenStatus = "pending"
    chosen: Optional[ChosenVariant] = None
    iterations: int = 0
    change_requests: list[ChangeRequest] = field(default_factory=list)
    svg_final: str = ""             # final SVG string after all changes
    decided_at: str = ""
    notes: str = ""

    @property
    def chosen_intent(self) -> str:
        if self.chosen == "A":
            return self.variant_a_intent
        if self.chosen == "B":
            return self.variant_b_intent
        return ""

    @property
    def is_decided(self) -> bool:
        return self.status == "decided"

    @property
    def iterations_remaining(self) -> int:
        return MAX_ITERATIONS_PER_SCREEN - self.iterations

    def decide(self, variant: ChosenVariant, svg_final: str = "") -> None:
        self.chosen = variant
        self.status = "decided"
        self.decided_at = datetime.now(timezone.utc).isoformat()
        if svg_final:
            self.svg_final = svg_final

    def add_change_request(self, description: str, base_variant: str = "A") -> ChangeRequest:
        self.iterations += 1
        self.status = "iterating"
        cr = ChangeRequest(
            iteration=self.iterations,
            description=description,
            base_variant=base_variant,
        )
        self.change_requests.append(cr)
        return cr

    def block(self, reason: str) -> None:
        self.status = "blocked"
        self.notes = reason

    def to_summary_row(self) -> str:
        variant = self.chosen or "—"
        cr_count = len(self.change_requests)
        return (
            f"| {self.screen_id} — {self.screen_name} "
            f"| {self.dimension} "
            f"| {variant} — {self.chosen_intent[:60]} "
            f"| {self.iterations} |"
        )


# ------------------------------------------------------------------
# Screen extraction helpers
# ------------------------------------------------------------------


_UC_PATTERN = re.compile(r"UC\d+", re.IGNORECASE)
_SCREEN_HINTS = [
    # (section_marker, screen_label_template)
    (r"##\s+UC\d+.*Lista|##\s+UC\d+.*Listagem", "Listagem"),
    (r"##\s+UC\d+.*Criar|##\s+UC\d+.*Adicionar|##\s+UC\d+.*Cadastr", "Formulário de Criação"),
    (r"##\s+UC\d+.*Editar|##\s+UC\d+.*Atualizar", "Formulário de Edição"),
    (r"##\s+UC\d+.*Excluir|##\s+UC\d+.*Deletar|##\s+UC\d+.*Remover", "Confirmação de Exclusão"),
    (r"##\s+UC\d+.*Filtrar|##\s+UC\d+.*Buscar|##\s+UC\d+.*Pesquisar", "Filtro / Busca"),
    (r"##\s+UC\d+.*Login|##\s+UC\d+.*Auth|##\s+UC\d+.*Entrar", "Tela de Login"),
    (r"WHILE.*lista.*vazia|WHILE.*sem.*itens|WHILE.*empty", "Estado Vazio"),
    (r"WHILE.*carregando|WHILE.*loading", "Estado de Carregamento"),
]

_DEFAULT_DIMENSIONS: dict[str, str] = {
    "Listagem": "posição dos filtros (topo vs rodapé)",
    "Formulário de Criação": "layout dos campos (single-column vs two-column)",
    "Formulário de Edição": "layout dos campos (single-column vs two-column)",
    "Confirmação de Exclusão": "padrão de confirmação (modal vs inline)",
    "Filtro / Busca": "posição da busca (topbar vs sidebar)",
    "Tela de Login": "layout do card (centrado vs full-left)",
    "Estado Vazio": "call-to-action (inline vs floating button)",
    "Estado de Carregamento": "indicador de progresso (skeleton vs spinner)",
}


def _infer_dimension(screen_name: str) -> str:
    for key, dim in _DEFAULT_DIMENSIONS.items():
        if key.lower() in screen_name.lower():
            return dim
    return "densidade visual (compact vs spacious)"


# ------------------------------------------------------------------
# Proto Generator
# ------------------------------------------------------------------


class ProtoGenerator:
    """Manages the full A/B wireframe decision lifecycle for a plan."""

    def __init__(self, plan_name: str, spec_path: "str | Path") -> None:
        self.plan_name = plan_name
        self.spec_path = Path(spec_path)
        self._screens: list[ScreenDecision] = []

    # ------------------------------------------------------------------
    # Screen extraction
    # ------------------------------------------------------------------

    def extract_screens(self) -> list[ScreenDecision]:
        """
        Parse spec.md and infer screen candidates from UCs, EARS requirements,
        and entity mentions. Returns the list and populates self._screens.
        """
        if not self.spec_path.exists():
            raise FileNotFoundError(f"spec.md not found at {self.spec_path}")

        content = self.spec_path.read_text(encoding="utf-8")
        screens: list[ScreenDecision] = []
        seen: set[str] = set()

        # Extract UC drilldown blocks → one screen per UC with UI relevance
        uc_blocks = re.findall(
            r"#{2,4}\s+(UC\d+[^#\n]*)\n(.*?)(?=\n#{2,4}|\Z)", content, re.DOTALL
        )
        for i, (uc_title, uc_body) in enumerate(uc_blocks, 1):
            uc_ids = _UC_PATTERN.findall(uc_title)
            label = uc_title.strip()
            key = label[:30].lower()
            if key in seen:
                continue
            seen.add(key)

            # Infer screen name from UC title
            screen_name = self._infer_screen_name(label)
            dimension = _infer_dimension(screen_name)
            screen_id = f"S{i:02d}"

            screens.append(
                ScreenDecision(
                    screen_id=screen_id,
                    screen_name=screen_name,
                    source_ucs=uc_ids,
                    dimension=dimension,
                    variant_a_intent="",
                    variant_b_intent="",
                )
            )

        # Extract WHILE/WHERE states → empty states, loading, etc.
        special_states = re.findall(
            r"(WHILE\s+[^\n]+|WHERE\s+[^\n]+)", content, re.IGNORECASE
        )
        for state in special_states:
            for pattern, label in _SCREEN_HINTS[-2:]:  # only state hints
                if re.search(pattern, state, re.IGNORECASE):
                    key = label[:30].lower()
                    if key not in seen:
                        seen.add(key)
                        sid = f"S{len(screens) + 1:02d}"
                        screens.append(
                            ScreenDecision(
                                screen_id=sid,
                                screen_name=label,
                                source_ucs=[],
                                dimension=_infer_dimension(label),
                                variant_a_intent="",
                                variant_b_intent="",
                            )
                        )

        self._screens = screens
        return screens

    def _infer_screen_name(self, uc_title: str) -> str:
        title = uc_title.lower()
        if any(w in title for w in ["lista", "listagem", "listar", "exibir"]):
            return "Listagem"
        if any(w in title for w in ["criar", "adicionar", "cadastrar", "novo"]):
            return "Formulário de Criação"
        if any(w in title for w in ["editar", "atualizar", "modificar"]):
            return "Formulário de Edição"
        if any(w in title for w in ["excluir", "deletar", "remover"]):
            return "Confirmação de Exclusão"
        if any(w in title for w in ["filtrar", "buscar", "pesquisar"]):
            return "Filtro / Busca"
        if any(w in title for w in ["login", "autenticar", "entrar"]):
            return "Tela de Login"
        # Fallback: use UC title words
        words = re.sub(r"UC\d+\s*[:—-]?\s*", "", uc_title).strip()
        return words[:40] if words else uc_title[:40]

    # ------------------------------------------------------------------
    # Decision recording
    # ------------------------------------------------------------------

    def record_decision(
        self,
        screen_id: str,
        screen_name: str,
        dimension: str,
        variant_a_intent: str,
        variant_b_intent: str,
        chosen: ChosenVariant,
        change_requests: Optional[list[str]] = None,
        svg_final: str = "",
        source_ucs: Optional[list[str]] = None,
    ) -> ScreenDecision:
        """Record a fully resolved screen decision."""
        screen = self._get_or_create(screen_id, screen_name, source_ucs or [])
        screen.dimension = dimension
        screen.variant_a_intent = variant_a_intent
        screen.variant_b_intent = variant_b_intent

        for cr_text in (change_requests or []):
            screen.add_change_request(cr_text)

        screen.decide(chosen, svg_final)
        return screen

    def apply_change_request(
        self, screen_id: str, description: str, base_variant: str = "A"
    ) -> ScreenDecision:
        """
        Register a change request for a screen mid-iteration.
        Raises RuntimeError if max iterations exceeded.
        """
        screen = self._get(screen_id)
        if screen.iterations >= MAX_ITERATIONS_PER_SCREEN:
            raise RuntimeError(
                f"Screen {screen_id} reached max iterations ({MAX_ITERATIONS_PER_SCREEN}). "
                "Force a decision (A or B) to proceed."
            )
        screen.add_change_request(description, base_variant)
        return screen

    def block_screen(self, screen_id: str, reason: str) -> ScreenDecision:
        """Block a screen that requires spec changes before continuing."""
        screen = self._get(screen_id)
        screen.block(reason)
        return screen

    # ------------------------------------------------------------------
    # Inventory helpers
    # ------------------------------------------------------------------

    def get_pending(self) -> list[ScreenDecision]:
        return [s for s in self._screens if s.status == "pending"]

    def get_decided(self) -> list[ScreenDecision]:
        return [s for s in self._screens if s.is_decided]

    def get_blocked(self) -> list[ScreenDecision]:
        return [s for s in self._screens if s.status == "blocked"]

    @property
    def is_complete(self) -> bool:
        return all(s.is_decided for s in self._screens)

    def inventory_markdown(self) -> str:
        status_icon = {"pending": "[ ]", "iterating": "[~]", "decided": "[x]", "blocked": "[!]"}
        lines = [f"📋 Screens identificadas para /proto ({self.plan_name}):\n"]
        for s in self._screens:
            icon = status_icon.get(s.status, "[ ]")
            ucs = ", ".join(s.source_ucs) if s.source_ucs else "—"
            lines.append(f"  {icon} {s.screen_id} — {s.screen_name} ({ucs})")
        decided = len(self.get_decided())
        pending = len(self.get_pending())
        blocked = len(self.get_blocked())
        lines.append(
            f"\nTotal: {len(self._screens)} screens | "
            f"{decided} decided | {pending} pending | {blocked} blocked"
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: "str | Path") -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "plan_name": self.plan_name,
            "total_screens": len(self._screens),
            "decided": len(self.get_decided()),
            "pending": len(self.get_pending()),
            "blocked": len(self.get_blocked()),
            "complete": self.is_complete,
            "screens": [asdict(s) for s in self._screens],
        }
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        return p

    @classmethod
    def load(cls, path: "str | Path", spec_path: "str | Path") -> "ProtoGenerator":
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        generator = cls(plan_name=payload["plan_name"], spec_path=spec_path)
        for raw in payload.get("screens", []):
            crs = [ChangeRequest(**cr) for cr in raw.pop("change_requests", [])]
            screen = ScreenDecision(**raw, change_requests=crs)
            generator._screens.append(screen)
        return generator

    # ------------------------------------------------------------------
    # Wireframes summary
    # ------------------------------------------------------------------

    def export_wireframes_md(self, path: "str | Path") -> Path:
        """Generate wireframes.md with decisions table and per-screen annotations."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# Wireframes: {self.plan_name}\n",
            "> Gerado por Framework Nexus `/proto`  \n",
            f"> Data: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}  \n",
            f"> Screens: {len(self.get_decided())}/{len(self._screens)} decided\n",
            "---\n",
            "## Decisões Visuais\n",
            "| Screen | Dimensão | Escolha | Iterações |",
            "|--------|----------|---------|-----------|",
        ]

        for s in self._screens:
            lines.append(s.to_summary_row())

        lines += ["\n---\n", "## Anotações de Intenção por Screen\n"]

        for s in self.get_decided():
            lines += [
                f"### {s.screen_id} — {s.screen_name}\n",
                f"**Variante escolhida:** {s.chosen}  ",
                f"**Dimensão em disputa:** {s.dimension}  ",
                f"**Intenção:** {s.chosen_intent}\n",
            ]
            if s.change_requests:
                lines.append("**Change requests aplicados:**")
                for cr in s.change_requests:
                    lines.append(f"- [{cr.iteration}] {cr.description} (base: {cr.base_variant})")
                lines.append("")
            if s.svg_final:
                lines += ["\n<details>", "<summary>SVG final</summary>\n",
                          s.svg_final, "\n</details>\n"]

        if self.get_blocked():
            lines += ["\n---\n", "## ⚠️ Screens Bloqueadas (requerem atualização do spec.md)\n"]
            for s in self.get_blocked():
                lines.append(f"- **{s.screen_id} — {s.screen_name}:** {s.notes}")

        p.write_text("\n".join(lines), encoding="utf-8")
        return p

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get(self, screen_id: str) -> ScreenDecision:
        for s in self._screens:
            if s.screen_id == screen_id:
                return s
        raise KeyError(f"Screen {screen_id} not found.")

    def _get_or_create(
        self, screen_id: str, screen_name: str, source_ucs: list[str]
    ) -> ScreenDecision:
        try:
            return self._get(screen_id)
        except KeyError:
            screen = ScreenDecision(
                screen_id=screen_id,
                screen_name=screen_name,
                source_ucs=source_ucs,
                dimension="",
                variant_a_intent="",
                variant_b_intent="",
            )
            self._screens.append(screen)
            return screen
