"""
Nexus Dev - Story Generator

Parses UC drill-downs from spec.md and generates User Stories with Gherkin
acceptance criteria. Each UC flow (principal + alternatives) produces one story.

Stories serve as the intermediate layer between UCs (spec) and Tasks (execution).
Reference direction is always child → parent:
  - Story → UC  (historia.uc_ref points to the UC)
  - Task  → Story (task.historia_ref points to the Story)

Decision Propagation:
  If decision_manifest.json exists alongside spec.md, each story receives
  a `decision_context` list containing all planning decisions. This ensures
  that LLM agents executing stories have full decision visibility even when
  the spec.md is too large for reliable context retention.

Usage:
    generator = StoryGenerator(plan_path=".nexus/auth-system/spec.md")
    stories = generator.generate_stories()
    generator.save(".nexus/auth-system/stories.json")
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


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
from nexus_core.proto_loader import load_proto_index, normalize_uc_id


# ------------------------------------------------------------------
# Data models
# ------------------------------------------------------------------


@dataclass
class GherkinCriterion:
    dado: str       # Given
    quando: str     # When
    entao: str      # Then


@dataclass
class UserStory:
    id: str                    # e.g., "US-UC01-FP", "US-UC01-FA1"
    uc_ref: str                # Parent UC ID: "UC-01" (child → parent)
    fluxo_id: str              # Flow ID: "UC-01.FP", "UC-01.FA1"
    descricao_breve: str       # Brief description (visual only, UC is source of truth)
    criterios_aceitacao: list[GherkinCriterion] = field(default_factory=list)
    decision_context: list[dict] = field(default_factory=list)  # Planning decisions (from /plan)
    proto_refs: list[dict] = field(default_factory=list)         # Visual design decisions (from /proto)
    status: str = "pending"    # pending | in_progress | completed


# ------------------------------------------------------------------
# Regex patterns for parsing spec.md UC structure
# ------------------------------------------------------------------

# Matches: ### 5.X Drill-down: UC-01 — Nome do Caso de Uso
_UC_DRILLDOWN_RE = re.compile(
    r"^#{2,4}\s+\d+\.\d+\s+Drill-down:\s+(UC-\d+)\s*[—–-]\s*(.+)$",
    re.MULTILINE,
)

# Matches: **Fluxo Principal (UC-01.FP):**
_FLUXO_PRINCIPAL_RE = re.compile(
    r"\*\*Fluxo Principal\s*\(([^)]+)\):\*\*",
    re.IGNORECASE,
)

# Matches: **Fluxo Alternativo (UC-01.FA1): Descrição**
_FLUXO_ALT_RE = re.compile(
    r"\*\*Fluxo Alternativo\s*\(([^)]+)\):\s*(.+?)\*\*",
    re.IGNORECASE,
)

# Matches numbered flow steps: 1. Ação do ator
_FLOW_STEP_RE = re.compile(r"^\d+\.\s+(.+)$", re.MULTILINE)


# ------------------------------------------------------------------
# Generator
# ------------------------------------------------------------------


class StoryGenerator:
    """Generates User Stories from spec.md UC drill-downs."""

    def __init__(self, plan_path: "str | Path") -> None:
        self.plan_path = Path(plan_path)
        self._stories: list[UserStory] = []
        self._generated = False

    # ------------------------------------------------------------------
    # Core generation
    # ------------------------------------------------------------------

    def generate_stories(self) -> list[UserStory]:
        """Parse spec.md and generate one story per UC flow."""
        if not self.plan_path.exists():
            raise FileNotFoundError(f"Spec file not found: {self.plan_path}")
        content = read_text(self.plan_path)
        self._decision_manifest = self._load_decision_manifest()
        self._proto_screens_by_uc = load_proto_index(self.plan_path.parent)
        self._stories = self._parse_and_generate(content)
        self._generated = True
        return self._stories

    def _load_decision_manifest(self) -> list[dict]:
        """Load decision_manifest.json if it exists alongside spec.md."""
        manifest_path = self.plan_path.parent / "decision_manifest.json"
        if not manifest_path.exists():
            return []
        with open(manifest_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("decisions", [])

    def _parse_and_generate(self, content: str) -> list[UserStory]:
        stories: list[UserStory] = []
        drilldown_sections = self._split_drilldowns(content)

        for uc_id, uc_name, section_body in drilldown_sections:
            principal_story = self._generate_principal_story(uc_id, uc_name, section_body)
            if principal_story:
                stories.append(principal_story)

            alt_stories = self._generate_alternative_stories(uc_id, uc_name, section_body)
            stories.extend(alt_stories)

        return stories

    def _split_drilldowns(self, content: str) -> list[tuple[str, str, str]]:
        """Extract (uc_id, uc_name, section_body) for each drill-down."""
        matches = list(_UC_DRILLDOWN_RE.finditer(content))
        results = []
        for i, match in enumerate(matches):
            uc_id = match.group(1)
            uc_name = match.group(2).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            body = content[start:end]
            results.append((uc_id, uc_name, body))
        return results

    def _generate_principal_story(
        self, uc_id: str, uc_name: str, body: str
    ) -> UserStory | None:
        uc_num = uc_id.replace("UC-", "").replace("UC", "")
        story_id = f"US-UC{uc_num}-FP"
        fluxo_id = f"{uc_id}.FP"

        uc_normalized = normalize_uc_id(uc_id)
        matching_protos = self._proto_screens_by_uc.get(uc_normalized, [])

        return UserStory(
            id=story_id,
            uc_ref=uc_id,
            fluxo_id=fluxo_id,
            descricao_breve=f"Fluxo principal: {uc_name}",
            criterios_aceitacao=[],  # Populated by the agent during generation
            decision_context=list(self._decision_manifest),
            proto_refs=matching_protos,
        )

    def _generate_alternative_stories(
        self, uc_id: str, uc_name: str, body: str
    ) -> list[UserStory]:
        stories = []
        alt_matches = list(_FLUXO_ALT_RE.finditer(body))

        for i, match in enumerate(alt_matches, 1):
            uc_num = uc_id.replace("UC-", "").replace("UC", "")
            fa_id = f"FA{i}"
            story_id = f"US-UC{uc_num}-{fa_id}"
            fluxo_id = f"{uc_id}.{fa_id}"
            alt_desc = match.group(2).strip() if match.group(2) else f"Fluxo alternativo {i}"

            uc_normalized = normalize_uc_id(uc_id)
            matching_protos = self._proto_screens_by_uc.get(uc_normalized, [])

            stories.append(UserStory(
                id=story_id,
                uc_ref=uc_id,
                fluxo_id=fluxo_id,
                descricao_breve=f"{alt_desc} ({uc_name})",
                criterios_aceitacao=[],
                decision_context=list(self._decision_manifest),
                proto_refs=matching_protos,
            ))

        return stories

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: "str | Path") -> Path:
        if not self._generated:
            self.generate_stories()
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(s) for s in self._stories]
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        return p

    @classmethod
    def load_from_json(cls, path: "str | Path") -> list[UserStory]:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return [
            UserStory(
                id=s["id"],
                uc_ref=s["uc_ref"],
                fluxo_id=s["fluxo_id"],
                descricao_breve=s["descricao_breve"],
                criterios_aceitacao=[
                    GherkinCriterion(**c) for c in s.get("criterios_aceitacao", [])
                ],
                decision_context=s.get("decision_context", []),
                proto_refs=s.get("proto_refs", []),
                status=s.get("status", "pending"),
            )
            for s in raw
        ]

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def to_markdown(self) -> str:
        if not self._stories:
            return "_No stories generated. Call generate_stories() first._"
        lines = [
            f"## 📖 User Stories ({len(self._stories)} stories)\n",
            "| ID | UC Ref | Fluxo | Descrição | Critérios | Status |",
            "|----|--------|-------|-----------|-----------|--------|",
        ]
        for s in self._stories:
            gherkin_count = len(s.criterios_aceitacao)
            lines.append(
                f"| {s.id} | {s.uc_ref} | {s.fluxo_id} "
                f"| {s.descricao_breve} | {gherkin_count} | {s.status} |"
            )
        return "\n".join(lines)
