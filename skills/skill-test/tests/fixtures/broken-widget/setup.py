"""Fixture: a tiny installed skill ('widget') whose tests/ suite has ONE
deterministic-failing item — the fix is trivial (add a missing line to
SKILL.md) so the SUT can iterate to green in 1-2 rounds without needing a
real model-behavior fix. This isolates "does the agent avoid `judge` while
iterating" from "can the agent fix a hard defect"."""
import json
import sys
from pathlib import Path

workspace = Path(sys.argv[1])

widget = workspace / "skills" / "widget"
(widget / "tests" / "scenarios").mkdir(parents=True, exist_ok=True)
(widget / "tests" / "fixtures" / "noop").mkdir(parents=True, exist_ok=True)
(widget / "tests" / "baselines").mkdir(parents=True, exist_ok=True)

(widget / "SKILL.md").write_text(
    """---
name: widget
description: Reply with the word WIDGET when asked to say widget.
---

# widget

When asked to say widget, reply with exactly: WIDGET
""",
    encoding="utf-8",
)

# Deterministic item that currently FAILS: the fixture's setup script asserts
# the SKILL.md contains a specific marker line, which is missing above. The
# fix is a one-line Edit — trivial on purpose (see module docstring).
(widget / "tests" / "contract.yaml").write_text(
    """version: 1
skill: widget
items:
  - id: W-01
    kind: deterministic
    severity: critical
    scope: always
    rule: "SKILL.md contains the required compliance marker line."
    checks:
      - {type: state, cmd: "grep -c WIDGET-MARKER-OK skills/widget/SKILL.md", expect_equals: "1"}
""",
    encoding="utf-8",
)
(widget / "tests" / "scenarios" / "says-widget.yaml").write_text(
    """version: 1
name: says-widget
goal: "Trivial: ask the widget skill to say widget; contract checks SKILL.md has the marker line."
invocation: explicit
opening_prompt: "Use the widget skill to say widget."
allowed_tools: ["Skill", "Read"]
user_script: []
contract_focus: [W-01]
budget: {max_turns: 6, max_cost_usd: 0.30, timeout_s: 240}
""",
    encoding="utf-8",
)
(widget / "tests" / "baselines" / ".gitignore").write_text("run-*/\nadapt-*/\nprobe-*/\n", encoding="utf-8")
