"""
Nexus Plan - Prompt Expander

Takes a raw user prompt and produces a structured discovery form with:
  1. Grouped discovery questions with A/B options
  2. XML-formatted prompt suitable for the spec_builder

Usage:
    expander = PromptExpander()
    form = expander.build_discovery_form(user_prompt, plan_name)
    print(form.to_markdown())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ------------------------------------------------------------------
# Discovery questions by category
# ------------------------------------------------------------------

_BASE_QUESTIONS: list[dict] = [
    {
        "category": "Functional",
        "question": "What is the primary goal of this feature/system?",
        "option_a": "Provide a CRUD interface for managing domain entities",
        "option_b": "Orchestrate a multi-step workflow between services",
        "recommendation": "A",
        "rationale": "CRUD is safer to scope; choose B if the prompt implies event-driven flow.",
    },
    {
        "category": "Users",
        "question": "Who are the primary users and what is their technical level?",
        "option_a": "End users (non-technical) interacting via a UI",
        "option_b": "Developers/operators consuming an API or CLI",
        "recommendation": "A",
        "rationale": "Default to end-user unless the prompt mentions API-first or admin tooling.",
    },
    {
        "category": "Auth",
        "question": "What authentication/authorization model is required?",
        "option_a": "Session-based auth (JWT / cookies) with role-based access",
        "option_b": "API key / OAuth2 with scopes",
        "recommendation": "A",
        "rationale": "Session-based is simpler for user-facing products; OAuth2 for platform APIs.",
    },
    {
        "category": "Persistence",
        "question": "What is the data persistence strategy?",
        "option_a": "Relational database (PostgreSQL / MySQL)",
        "option_b": "Document store (MongoDB / DynamoDB)",
        "recommendation": "A",
        "rationale": "Relational is default unless domain is schema-flexible or document-oriented.",
    },
    {
        "category": "Non-Functional",
        "question": "What are the performance/availability requirements?",
        "option_a": "Standard web expectations: <500ms p95, 99.5% uptime",
        "option_b": "High-performance / HA: <100ms p99, 99.99% uptime with failover",
        "recommendation": "A",
        "rationale": "Option A cover most products; use B only for proven high-load requirement.",
    },
    {
        "category": "Security",
        "question": "Does this feature handle sensitive data (PII, payments, health)?",
        "option_a": "Yes — must comply with LGPD/GDPR, PCI-DSS, or equivalent",
        "option_b": "No — standard secure coding practices are sufficient",
        "recommendation": "B",
        "rationale": "Most features do not; escalate to A only if confirmed by stakeholder.",
    },
    {
        "category": "Testing",
        "question": "What is the minimum acceptable test coverage strategy?",
        "option_a": "Unit + integration tests, ≥80% line coverage",
        "option_b": "Unit tests only, ≥60% coverage (faster delivery)",
        "recommendation": "A",
        "rationale": "Nexus enforces evidence-based homologation; A makes /review simpler.",
    },
    {
        "category": "Deployment",
        "question": "What is the deployment/delivery target?",
        "option_a": "Containerised (Docker + CI/CD pipeline)",
        "option_b": "Serverless / PaaS (Lambda, Cloud Run, Vercel)",
        "recommendation": "A",
        "rationale": "Containers offer more portability; serverless if cold-start and vendor lock-in are acceptable.",
    },
]

_INTEGRATION_QUESTIONS: list[dict] = [
    {
        "category": "External APIs",
        "question": "How should failures in external API calls be handled?",
        "option_a": "Retry with exponential back-off (max 3 attempts), then circuit-break",
        "option_b": "Fail fast with a clear error message to the caller",
        "recommendation": "A",
        "rationale": "Resilient by default; choose B only for synchronous user-facing flows.",
    },
]

_INFRA_QUESTIONS: list[dict] = [
    {
        "category": "Migrations",
        "question": "How should database schema changes be managed?",
        "option_a": "Versioned migration files (Alembic, Flyway, Liquibase)",
        "option_b": "ORM auto-migrate on startup",
        "recommendation": "A",
        "rationale": "Auto-migrate is dangerous in production; versioned migrations are the standard.",
    },
]


# ------------------------------------------------------------------
# Discovery form
# ------------------------------------------------------------------

@dataclass
class DiscoveryQuestion:
    category: str
    question: str
    option_a: str
    option_b: str
    recommendation: str  # "A" or "B"
    rationale: str
    answered: Optional[str] = None  # "A", "B", or free-text

    def to_markdown(self, index: int) -> str:
        rec_marker_a = " ← **recommended**" if self.recommendation == "A" else ""
        rec_marker_b = " ← **recommended**" if self.recommendation == "B" else ""
        return (
            f"**Q{index}. [{self.category}]** {self.question}\n"
            f"  - **A)** {self.option_a}{rec_marker_a}\n"
            f"  - **B)** {self.option_b}{rec_marker_b}\n"
            f"  > _Rationale: {self.rationale}_"
        )


@dataclass
class DiscoveryForm:
    plan_name: str
    raw_prompt: str
    questions: list[DiscoveryQuestion] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            f"# 🔍 Discovery Form — {self.plan_name}\n",
            f"> Original prompt: _{self.raw_prompt}_\n",
            "---\n",
            "## ❓ Discovery Questions\n",
            "*Please answer each question (A / B / custom):*\n",
        ]
        for i, q in enumerate(self.questions, 1):
            lines.append(q.to_markdown(i))
            lines.append("")
        lines += [
            "---",
            "\n> **State:** `WAITING_FOR_DISCOVERY_INPUT`  ",
            "> Respond to all questions above, then invoke `/plan` again to generate the plan.",
        ]
        return "\n".join(lines)

    def apply_answers(self, answers: dict[int, str]) -> None:
        """Apply user answers (1-indexed) to questions."""
        for idx, answer in answers.items():
            if 1 <= idx <= len(self.questions):
                self.questions[idx - 1].answered = answer

    @property
    def all_answered(self) -> bool:
        return all(q.answered is not None for q in self.questions)

    def resolve_defaults(self) -> None:
        """Fill unanswered questions with their recommended option (auto-assumption)."""
        for q in self.questions:
            if q.answered is None:
                q.answered = q.recommendation


# ------------------------------------------------------------------
# Main expander
# ------------------------------------------------------------------

class PromptExpander:
    """Transforms a raw user prompt into a structured discovery form."""

    def build_discovery_form(self, raw_prompt: str, plan_name: str) -> DiscoveryForm:
        """Build a DiscoveryForm with all discovery questions."""
        questions_dicts = list(_BASE_QUESTIONS) + list(_INTEGRATION_QUESTIONS) + list(_INFRA_QUESTIONS)
        questions = [DiscoveryQuestion(**q) for q in questions_dicts]
        return DiscoveryForm(
            plan_name=plan_name,
            raw_prompt=raw_prompt,
            questions=questions,
        )

    def to_xml_prompt(
        self, raw_prompt: str, plan_name: str, tech_stack: str = "to be determined"
    ) -> str:
        """Produce a GSD-style XML-formatted prompt for the plan generator."""
        return (
            f"<prompt>\n"
            f"  <role>nexus_spec_planner</role>\n"
            f"  <context>\n"
            f"    <project_name>{plan_name}</project_name>\n"
            f"    <tech_stack>{tech_stack}</tech_stack>\n"
            f"  </context>\n"
            f"  <user_request>{raw_prompt}</user_request>\n"
            f"  <task>Generate a complete spec-driven plan following EARS notation.</task>\n"
            f"  <constraints>\n"
            f"    <no_code>true — planning phase only</no_code>\n"
            f"    <ears_required>true</ears_required>\n"
            f"    <ambiguity_threshold>zero</ambiguity_threshold>\n"
            f"  </constraints>\n"
            f"  <output_format>markdown plan document</output_format>\n"
            f"</prompt>"
        )


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Build a delivery app with payment integration"
    plan_name = prompt.lower().replace(" ", "-")[:30]
    expander = PromptExpander()
    form = expander.build_discovery_form(prompt, plan_name)
    print(form.to_markdown())
    print("\n--- XML Prompt ---\n")
    print(expander.to_xml_prompt(prompt, plan_name))
