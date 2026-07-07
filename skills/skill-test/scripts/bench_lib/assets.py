"""Loading + validation of tests/ assets: contract.yaml and scenarios/*.yaml."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .config import BenchError
from .util import load_structured

VALID_KINDS = {"deterministic", "judge"}
VALID_SEVERITIES = {"critical", "major", "minor"}
VALID_SCOPES = {"always", "focused"}
VALID_CHECK_TYPES = {"state", "file_exists", "file_absent", "required_event", "forbidden_event"}
SEVERITY_WEIGHT = {"critical": 4, "major": 2, "minor": 1}


def tests_dir(skill_dir: Path) -> Path:
    return skill_dir / "tests"


def load_contract(skill_dir: Path) -> dict:
    path = tests_dir(skill_dir) / "contract.yaml"
    if not path.exists():
        path_json = path.with_suffix(".json")
        if path_json.exists():
            path = path_json
        else:
            raise BenchError(
                f"no contract at {path}",
                next_step="run `test_tool.py init --skill <name>` to scaffold, then author contract.yaml items (see skill-test references/authoring.md)",
            )
    contract = load_structured(path)
    items = contract.get("items") or []
    if not items:
        raise BenchError(f"{path.name} has no items",
                         next_step="author at least one contract item — see skill-test references/authoring.md §contract")
    seen: set[str] = set()
    for it in items:
        iid = it.get("id")
        if not iid or iid in seen:
            raise BenchError(f"contract item with missing/duplicate id: {iid!r}")
        seen.add(iid)
        if it.get("kind") not in VALID_KINDS:
            raise BenchError(f"{iid}: kind must be one of {sorted(VALID_KINDS)}")
        if it.get("severity") not in VALID_SEVERITIES:
            raise BenchError(f"{iid}: severity must be one of {sorted(VALID_SEVERITIES)}")
        it.setdefault("scope", "focused")
        if it["scope"] not in VALID_SCOPES:
            raise BenchError(f"{iid}: scope must be one of {sorted(VALID_SCOPES)}")
        if not it.get("rule"):
            raise BenchError(f"{iid}: missing rule text")
        checks = it.get("checks") or ([it["check"]] if it.get("check") else [])
        it["checks"] = checks
        if it["kind"] == "deterministic":
            if not checks:
                raise BenchError(f"{iid}: deterministic item needs checks")
            for c in checks:
                if c.get("type") not in VALID_CHECK_TYPES:
                    raise BenchError(f"{iid}: unknown check type {c.get('type')!r}")
    contract["_hash"] = hashlib.sha256(
        json.dumps(items, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:12]
    return contract


def contract_items_for_scenario(contract: dict, scenario: dict) -> list[dict]:
    focus = set(scenario.get("contract_focus") or [])
    picked = [it for it in contract["items"] if it["scope"] == "always" or it["id"] in focus]
    unknown = focus - {it["id"] for it in contract["items"]}
    if unknown:
        raise BenchError(f"scenario {scenario['name']}: unknown contract_focus ids {sorted(unknown)}")
    return picked


def load_scenarios(skill_dir: Path, selector: str) -> list[dict]:
    sdir = tests_dir(skill_dir) / "scenarios"
    if not sdir.is_dir():
        raise BenchError(f"no scenarios dir at {sdir}",
                         next_step="run `test_tool.py init --skill <name>` to scaffold tests/")
    available = sorted(list(sdir.glob("*.yaml")) + list(sdir.glob("*.json")))
    if not available:
        raise BenchError(f"no scenario files in {sdir}",
                         next_step="author a scenario yaml — copy tests/scenarios/example.yaml.disabled or see references/authoring.md")
    wanted = None if selector in ("all", "", None) else {s.strip() for s in selector.split(",")}
    scenarios = []
    for path in available:
        sc = load_structured(path)
        sc.setdefault("name", path.stem)
        if wanted is not None and sc["name"] not in wanted:
            continue
        _validate_scenario(sc, skill_dir)
        scenarios.append(sc)
    if wanted is not None:
        missing = wanted - {s["name"] for s in scenarios}
        if missing:
            raise BenchError(f"scenarios not found: {sorted(missing)}",
                         next_step=f"available: {[s['name'] for s in scenarios] or [p.stem for p in available]}")
    return scenarios


def _validate_scenario(sc: dict, skill_dir: Path) -> None:
    name = sc["name"]
    if not sc.get("opening_prompt"):
        raise BenchError(f"scenario {name}: missing opening_prompt")
    sc.setdefault("invocation", "auto")
    if sc["invocation"] not in ("auto", "explicit"):
        raise BenchError(f"scenario {name}: invocation must be auto|explicit")
    sc.setdefault("user_script", [])
    for step in sc["user_script"]:
        anchors = step.get("expect_any") or ([step["expect"]] if step.get("expect") else [])
        if not anchors:
            raise BenchError(f"scenario {name}: user_script step without expect/expect_any")
        step["expect_any"] = anchors
        if not (step.get("respond") or step.get("respond_label")):
            raise BenchError(f"scenario {name}: user_script step without respond/respond_label")
    sc.setdefault("on_desync", "fail")
    sc.setdefault("budget", {})
    fixture = sc.get("fixture")
    if fixture:
        setup = tests_dir(skill_dir) / "fixtures" / fixture / "setup.py"
        if not setup.exists():
            raise BenchError(f"scenario {name}: fixture setup not found at {setup}")
