#!/usr/bin/env python3
"""
SonarCloud CLI — Unified hub for health, issues, and fix support.

Subcommands:
  health   Project health dashboard (quality gate, coverage, ratings)
  issues   Search and categorize issues (by category, rule, or file)
  files    List files ranked by issue count
  rule     Fetch official rule details from SonarCloud

Usage:
  python sonar.py health
  python sonar.py health --project aigov-genai-api --branch develop
  python sonar.py issues --project aigov-genai-api
  python sonar.py issues --project aigov-genai-api --category security
  python sonar.py issues --project aigov-genai-api --file src/Infra/Repo.cs
  python sonar.py files  --project aigov-genai-api
  python sonar.py rule   --key csharpsquid:S6966

All flags are optional. When omitted, --project and --branch are auto-detected
from the local git repository.

Output: JSON to stdout. Diagnostic messages go to stderr.
"""

import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from html import unescape as html_unescape
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    sys.stderr.reconfigure(line_buffering=True, encoding="utf-8")

SONAR_API = "https://sonarcloud.io/api"
TOKEN_FILE = Path.home() / ".sonarcloud" / "token"

RATING_MAP = {"1.0": "A", "2.0": "B", "3.0": "C", "4.0": "D", "5.0": "E"}

HEALTH_METRICS = [
    "alert_status", "bugs", "vulnerabilities", "code_smells",
    "coverage", "duplicated_lines_density", "security_rating",
    "reliability_rating", "sqale_rating", "security_hotspots",
    "security_review_rating", "ncloc", "violations",
]

TYPE_TO_CATEGORY = {
    "VULNERABILITY": "Security",
    "SECURITY_HOTSPOT": "Security",
    "BUG": "Reliability",
    "CODE_SMELL": "Maintainability",
}

SEVERITY_ORDER = {"BLOCKER": 0, "CRITICAL": 1, "MAJOR": 2, "MINOR": 3, "INFO": 4}

HOTSPOT_PROBABILITY_TO_SEVERITY = {"HIGH": "CRITICAL", "MEDIUM": "MAJOR", "LOW": "MINOR"}


# ──────────────────────────────────────────────
# Common utilities
# ──────────────────────────────────────────────

def load_token():
    for var in ("SONAR_TOKEN", "SONARCLOUD_TOKEN", "SONAR_CLOUD"):
        token = os.environ.get(var, "").strip()
        if token:
            return token
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    return None


def api_get(endpoint, params, token):
    qs = "&".join(
        f"{k}={urllib.request.quote(str(v))}"
        for k, v in params.items()
        if v is not None
    )
    url = f"{SONAR_API}/{endpoint}{'?' + qs if qs else ''}"
    req = urllib.request.Request(url)
    cred = base64.b64encode(f"{token}:".encode()).decode()
    req.add_header("Authorization", f"Basic {cred}")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300] if e.fp else ""
        return None, {"code": e.code, "message": body}
    except Exception as e:
        return None, {"code": 0, "message": str(e)}


def detect_repo():
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        url = result.stdout.strip()
        if not url:
            return None
        name = url.rstrip("/").split("/")[-1]
        return name[:-4] if name.endswith(".git") else name
    except Exception:
        return None


def detect_branch():
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5,
        )
        branch = result.stdout.strip()
        return branch if branch else None
    except Exception:
        return None


def resolve_project_key(component, org, token):
    candidates = [component]
    if org:
        candidates.append(f"{org}_{component}")

    for key in candidates:
        data, _ = api_get("measures/component", {
            "component": key, "metricKeys": "ncloc",
        }, token)
        if data and "component" in data:
            return key, None

    if org:
        data, _ = api_get("projects/search", {
            "q": component, "organization": org,
        }, token)
        if data and data.get("components"):
            return data["components"][0]["key"], None

    data, _ = api_get("projects/search", {"q": component}, token)
    if data and data.get("components"):
        return data["components"][0]["key"], None

    return None, f"Projeto '{component}' nao encontrado no SonarCloud"


def to_rating(value):
    if value is None:
        return None
    return RATING_MAP.get(str(value), str(value))


def resolve_context(opts):
    """Resolve project, branch, org from flags + git auto-detection.

    Branch auto-detection only applies when the project is also auto-detected
    (same git repo). When --project is explicit and differs from the local repo,
    the git branch is irrelevant and we let the API use the project's default.
    """
    token = load_token()
    if not token:
        return None, None, None, None, "TOKEN_NOT_FOUND"

    explicit_project = opts.get("project")
    detected_repo = detect_repo()
    component = explicit_project or detected_repo
    if not component:
        return None, None, None, None, "REPO_NOT_DETECTED"

    project_is_local = not explicit_project or explicit_project == detected_repo

    if opts.get("branch"):
        branch = opts["branch"]
    elif project_is_local:
        branch = detect_branch()
    else:
        branch = None

    org = opts.get("org") or os.environ.get("SONAR_ORG", "").strip() or None

    project_key, err = resolve_project_key(component, org, token)
    if not project_key:
        return None, None, None, None, err

    return token, project_key, branch, org, None


def detect_org(project_key, token):
    """Detect organization from a known project via components/show."""
    env_org = os.environ.get("SONAR_ORG", "").strip()
    if env_org:
        return env_org
    if not project_key:
        return None
    data, _ = api_get("components/show", {"component": project_key}, token)
    if data and "component" in data:
        return data["component"].get("organization")
    return None


def fail(error_code, message=None):
    payload = {"error": error_code}
    if message:
        payload["message"] = message
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(1)


# ──────────────────────────────────────────────
# Path normalization & enrichment
# ──────────────────────────────────────────────

def strip_html_tags(html_code):
    """Strip HTML tags and unescape entities to produce plain source code."""
    if not html_code:
        return ""
    return html_unescape(re.sub(r"<[^>]+>", "", html_code))


def _repo_name_from_key(project_key):
    """Extract the repository name from a Sonar project key (handles org_repo)."""
    return project_key.rsplit("_", 1)[-1] if "_" in project_key else project_key


def strip_project_prefix(component_path, project_key):
    """Remove the Sonar-internal repo-name prefix so paths match the workspace.

    e.g. 'quality-hub-mcp/src/server.ts' -> 'src/server.ts'
    """
    prefix = f"{_repo_name_from_key(project_key)}/"
    if component_path.startswith(prefix):
        return component_path[len(prefix):]
    return component_path


def resolve_file_component_key(project_key, file_path, branch, token):
    """Resolve the correct Sonar component key for a workspace file path.

    The Sonar component key often includes an internal prefix
    (e.g. 'repo-name/src/...'). This function queries components/tree
    to find the exact key, falling back to heuristic prefixing.
    """
    basename = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
    params = {
        "component": project_key,
        "qualifiers": "FIL",
        "q": basename,
        "ps": 50,
    }
    if branch:
        params["branch"] = branch

    tree_data, tree_err = api_get("components/tree", params, token)

    if not tree_err and tree_data:
        for comp in tree_data.get("components", []):
            comp_key = comp.get("key", "")
            comp_path = comp_key.split(":", 1)[-1] if ":" in comp_key else ""
            if comp_path == file_path or comp_path.endswith(f"/{file_path}"):
                return comp_key

    repo_name = _repo_name_from_key(project_key)
    if not file_path.startswith(f"{repo_name}/"):
        return f"{project_key}:{repo_name}/{file_path}"
    return f"{project_key}:{file_path}"


def fetch_issue_snippets(issue_keys, token):
    """Fetch code snippets for a list of issue keys (sources/issue_snippets).

    Returns dict: {issue_key: {startLine, endLine, lines: [{line, code}]}}
    """
    snippets = {}
    for issue_key in issue_keys:
        data, err = api_get("sources/issue_snippets", {"issueKey": issue_key}, token)
        if err or not data:
            continue
        for _comp_key, comp_data in data.items():
            sources = comp_data.get("sources", [])
            if not sources:
                continue
            lines = [
                {"line": s.get("line"), "code": strip_html_tags(s.get("code", ""))}
                for s in sources
            ]
            snippets[issue_key] = {
                "startLine": sources[0].get("line"),
                "endLine": sources[-1].get("line"),
                "lines": lines,
            }
            break
    return snippets


def normalize_flows(raw_flows, project_key):
    """Normalize the flows/secondary-locations from the raw API response."""
    if not raw_flows:
        return []
    normalized = []
    for flow in raw_flows:
        locations = flow.get("locations", [])
        if not locations:
            continue
        norm_locs = []
        for loc in locations:
            comp = (loc.get("component") or "").split(":", 1)[-1]
            norm_locs.append({
                "file": strip_project_prefix(comp, project_key),
                "textRange": loc.get("textRange"),
                "message": loc.get("msg"),
            })
        normalized.append(norm_locs)
    return normalized


# ──────────────────────────────────────────────
# Subcommand: health
# ──────────────────────────────────────────────

def cmd_health(opts):
    token, project_key, branch, _, err = resolve_context(opts)
    if err:
        fail(err)

    sys.stderr.write(f"health | project={project_key} branch={branch or '(auto)'}\n")

    metrics_param = ",".join(HEALTH_METRICS)
    measures_data, api_err = api_get("measures/component", {
        "component": project_key,
        "branch": branch,
        "metricKeys": metrics_param,
    }, token)

    if api_err and api_err["code"] == 404 and branch:
        sys.stderr.write(f"Branch '{branch}' nao encontrada, usando default\n")
        branch = None
        measures_data, api_err = api_get("measures/component", {
            "component": project_key,
            "metricKeys": metrics_param,
        }, token)

    if api_err:
        fail("FETCH_FAILED", f"measures: HTTP {api_err['code']}: {api_err['message']}")

    metrics = {}
    for m in measures_data.get("component", {}).get("measures", []):
        metrics[m["metric"]] = m.get("value")

    qg_params = {"projectKey": project_key}
    if branch:
        qg_params["branch"] = branch
    qg_data, _ = api_get("qualitygates/project_status", qg_params, token)

    quality_gate = None
    if qg_data and "projectStatus" in qg_data:
        ps = qg_data["projectStatus"]
        conditions = [
            {
                "metric": c.get("metricKey"),
                "status": c.get("status"),
                "value": c.get("actualValue"),
                "threshold": c.get("errorThreshold"),
            }
            for c in ps.get("conditions", [])
        ]
        quality_gate = {"status": ps.get("status"), "conditions": conditions}

    analysis_data, _ = api_get("project_analyses/search", {
        "project": project_key, "ps": 1,
    }, token)

    last_analysis = None
    if analysis_data and analysis_data.get("analyses"):
        last_analysis = analysis_data["analyses"][0].get("date")

    result = {
        "project": project_key,
        "branch": branch or "(default)",
        "lastAnalysis": last_analysis,
        "linesOfCode": metrics.get("ncloc"),
        "qualityGate": quality_gate,
        "overview": {
            "openIssues": int(metrics.get("violations", 0)),
            "duplications": f"{metrics.get('duplicated_lines_density', '0')}%",
            "coverage": f"{metrics.get('coverage', '0')}%",
        },
        "security": {
            "rating": to_rating(metrics.get("security_rating")),
            "issues": int(metrics.get("vulnerabilities", 0)),
        },
        "securityHotspots": {
            "rating": to_rating(metrics.get("security_review_rating")),
            "count": int(metrics.get("security_hotspots", 0)),
        },
        "reliability": {
            "rating": to_rating(metrics.get("reliability_rating")),
            "issues": int(metrics.get("bugs", 0)),
        },
        "maintainability": {
            "rating": to_rating(metrics.get("sqale_rating")),
            "issues": int(metrics.get("code_smells", 0)),
        },
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


# ──────────────────────────────────────────────
# Subcommand: issues
# ──────────────────────────────────────────────

def fetch_issues(project_key, branch, token, file_path=None):
    """Fetch all open issues with pagination. Optionally filter by file (server-side)."""
    all_issues = []
    page = 1
    page_size = 500
    max_results = 2000
    total = 0

    if file_path:
        component_key = resolve_file_component_key(project_key, file_path, branch, token)
    else:
        component_key = project_key

    while True:
        params = {
            "componentKeys": component_key,
            "issueStatuses": "OPEN,CONFIRMED",
            "additionalFields": "_all",
            "p": page,
            "ps": page_size,
        }
        if branch:
            params["branch"] = branch

        data, api_err = api_get("issues/search", params, token)

        if api_err and api_err["code"] == 404 and branch:
            sys.stderr.write(f"Branch '{branch}' nao encontrada, usando default\n")
            params.pop("branch", None)
            data, api_err = api_get("issues/search", params, token)

        if api_err:
            return None, 0, f"issues/search: HTTP {api_err['code']}: {api_err['message']}"

        fetched = data.get("issues", [])
        total = data.get("total", 0)
        if not fetched:
            break

        all_issues.extend(fetched)
        if len(all_issues) >= total or len(all_issues) >= max_results:
            break
        page += 1

    normalized = []
    for raw in all_issues:
        component_path = (raw.get("component") or "").split(":", 1)[-1]
        raw_flows = raw.get("flows", [])
        entry = {
            "issueKey": raw.get("key"),
            "rule": raw.get("rule"),
            "file": strip_project_prefix(component_path, project_key),
            "line": raw.get("line"),
            "message": raw.get("message"),
            "severity": raw.get("severity"),
            "type": raw.get("type"),
            "effort": raw.get("effort"),
            "category": TYPE_TO_CATEGORY.get(raw.get("type"), "Maintainability"),
            "textRange": raw.get("textRange"),
        }
        flows = normalize_flows(raw_flows, project_key)
        if flows:
            entry["flows"] = flows
        normalized.append(entry)

    return normalized, total, None


def _resolve_hotspot_files_param(project_key, file_path):
    """Build the Sonar-internal file path for the hotspots/search `files` param."""
    repo_name = _repo_name_from_key(project_key)
    if file_path.startswith(f"{repo_name}/"):
        return file_path
    return f"{repo_name}/{file_path}"


def fetch_hotspots(project_key, branch, token, file_path=None):
    """Fetch all open security hotspots via the dedicated hotspots/search API."""
    all_hotspots = []
    page = 1
    page_size = 500
    max_results = 2000

    while True:
        params = {
            "projectKey": project_key,
            "status": "TO_REVIEW",
            "p": page,
            "ps": page_size,
        }
        if branch:
            params["branch"] = branch
        if file_path:
            params["files"] = _resolve_hotspot_files_param(project_key, file_path)

        data, api_err = api_get("hotspots/search", params, token)

        if api_err and api_err["code"] == 404 and branch:
            sys.stderr.write(f"Branch '{branch}' nao encontrada para hotspots, usando default\n")
            params.pop("branch", None)
            data, api_err = api_get("hotspots/search", params, token)

        if api_err:
            return None, 0, f"hotspots/search: HTTP {api_err['code']}: {api_err['message']}"

        paging = data.get("paging", {})
        fetched = data.get("hotspots", [])
        if not fetched:
            break

        all_hotspots.extend(fetched)
        api_total = paging.get("total", 0)
        if len(all_hotspots) >= api_total or len(all_hotspots) >= max_results:
            break
        page += 1

    normalized = []
    for raw in all_hotspots:
        component_path = (raw.get("component") or "").split(":", 1)[-1]
        norm_file = strip_project_prefix(component_path, project_key)

        prob = raw.get("vulnerabilityProbability", "MEDIUM")
        normalized.append({
            "issueKey": raw.get("key"),
            "rule": raw.get("ruleKey"),
            "file": norm_file,
            "line": raw.get("line"),
            "message": raw.get("message"),
            "severity": HOTSPOT_PROBABILITY_TO_SEVERITY.get(prob, "MAJOR"),
            "type": "SECURITY_HOTSPOT",
            "effort": None,
            "category": "Security",
            "textRange": raw.get("textRange"),
            "securityCategory": raw.get("securityCategory"),
            "vulnerabilityProbability": prob,
        })

    return normalized, len(normalized), None


def build_grouped_output(issues, total):
    """Format B: grouped by category > rule, sorted by severity."""
    groups = {}
    for issue in issues:
        cat = issue["category"]
        rule = issue["rule"]

        if cat not in groups:
            groups[cat] = {"count": 0, "byRule": {}}
        groups[cat]["count"] += 1

        if rule not in groups[cat]["byRule"]:
            groups[cat]["byRule"][rule] = {
                "count": 0,
                "severity": issue["severity"],
                "type": issue["type"],
                "issues": [],
            }
        rule_group = groups[cat]["byRule"][rule]
        rule_group["count"] += 1
        issue_entry = {
            "file": issue["file"],
            "line": issue["line"],
            "message": issue["message"],
            "effort": issue["effort"],
            "textRange": issue.get("textRange"),
        }
        if issue.get("flows"):
            issue_entry["flows"] = issue["flows"]
        rule_group["issues"].append(issue_entry)

    for cat_data in groups.values():
        cat_data["byRule"] = dict(sorted(
            cat_data["byRule"].items(),
            key=lambda x: (SEVERITY_ORDER.get(x[1]["severity"], 9), -x[1]["count"]),
        ))

    ordered = {}
    for cat in ["Security", "Reliability", "Maintainability"]:
        if cat in groups:
            ordered[cat] = groups[cat]

    return {
        "total": total,
        "fetched": len(issues),
        "summary": {cat: data["count"] for cat, data in ordered.items()},
        "categories": ordered,
    }


def build_file_output(issues, total, target_file):
    """Format C: flat list for a specific file, sorted by line."""
    sorted_issues = sorted(issues, key=lambda i: (i.get("line") or 0))
    result_issues = []
    for i in sorted_issues:
        entry = {
            "rule": i["rule"],
            "line": i["line"],
            "message": i["message"],
            "severity": i["severity"],
            "type": i["type"],
            "category": i["category"],
            "effort": i["effort"],
            "textRange": i.get("textRange"),
        }
        if i.get("flows"):
            entry["flows"] = i["flows"]
        if i.get("snippet"):
            entry["snippet"] = i["snippet"]
        result_issues.append(entry)
    return {
        "total": total,
        "file": target_file,
        "issueCount": len(result_issues),
        "issues": result_issues,
    }


def _should_include_hotspots(target_category):
    """Hotspots are included when no category filter or category is 'security'."""
    if not target_category:
        return True
    return target_category.lower() == "security"


def cmd_issues(opts):
    token, project_key, branch, _, err = resolve_context(opts)
    if err:
        fail(err)

    target_file = opts.get("file")
    target_category = opts.get("category")

    sys.stderr.write(
        f"issues | project={project_key} branch={branch or '(auto)'}"
        f"{' file=' + target_file if target_file else ''}"
        f"{' category=' + target_category if target_category else ''}\n"
    )

    issues, total, fetch_err = fetch_issues(project_key, branch, token, file_path=target_file)
    if fetch_err:
        fail("FETCH_FAILED", fetch_err)

    if _should_include_hotspots(target_category):
        hotspots, hotspot_total, hs_err = fetch_hotspots(
            project_key, branch, token, file_path=target_file,
        )
        if hs_err:
            sys.stderr.write(f"Warning: hotspots fetch failed: {hs_err}\n")
        elif hotspots:
            sys.stderr.write(f"Fetched {len(hotspots)} security hotspots\n")
            issues.extend(hotspots)
            total += hotspot_total

    if target_file:
        issue_keys = [i["issueKey"] for i in issues if i.get("issueKey")]
        if issue_keys:
            sys.stderr.write(f"Fetching snippets for {len(issue_keys)} issues...\n")
            snippets = fetch_issue_snippets(issue_keys, token)
            for issue in issues:
                key = issue.get("issueKey")
                if key and key in snippets:
                    issue["snippet"] = snippets[key]
        result = build_file_output(issues, len(issues), target_file)
    else:
        if target_category:
            cat_map = {
                "security": "Security",
                "reliability": "Reliability",
                "maintainability": "Maintainability",
            }
            cat_label = cat_map.get(target_category.lower())
            if cat_label:
                issues = [i for i in issues if i["category"] == cat_label]

        result = build_grouped_output(issues, len(issues))

    print(json.dumps(result, ensure_ascii=False, indent=2))


# ──────────────────────────────────────────────
# Subcommand: files
# ──────────────────────────────────────────────

def cmd_files(opts):
    token, project_key, branch, _, err = resolve_context(opts)
    if err:
        fail(err)

    sys.stderr.write(f"files | project={project_key} branch={branch or '(auto)'}\n")

    issues, total, fetch_err = fetch_issues(project_key, branch, token)
    if fetch_err:
        fail("FETCH_FAILED", fetch_err)

    hotspots, hotspot_total, hs_err = fetch_hotspots(project_key, branch, token)
    if hs_err:
        sys.stderr.write(f"Warning: hotspots fetch failed: {hs_err}\n")
    elif hotspots:
        sys.stderr.write(f"Fetched {len(hotspots)} security hotspots for file ranking\n")
        issues.extend(hotspots)
        total += hotspot_total

    file_stats = {}
    for issue in issues:
        f = issue["file"]
        if f not in file_stats:
            file_stats[f] = {"count": 0, "bySeverity": {}, "byCategory": {}}
        stats = file_stats[f]
        stats["count"] += 1

        sev = issue["severity"] or "UNKNOWN"
        stats["bySeverity"][sev] = stats["bySeverity"].get(sev, 0) + 1

        cat = issue["category"]
        stats["byCategory"][cat] = stats["byCategory"].get(cat, 0) + 1

    ranked = dict(sorted(file_stats.items(), key=lambda x: -x[1]["count"]))

    result = {
        "total": total,
        "fileCount": len(ranked),
        "files": ranked,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


# ──────────────────────────────────────────────
# Subcommand: rule
# ──────────────────────────────────────────────

def _parse_description_sections(raw_sections):
    """Parse descriptionSections into a structured dict.

    Sections without context are stored as plain strings.
    Sections with context (e.g. how_to_fix for NUnit/xUnit/MSTest)
    are stored as a dict keyed by the context displayName.
    """
    result = {}
    for sec in raw_sections:
        key = sec.get("key", "unknown")
        content = strip_html_tags(sec.get("content") or "").strip()
        context = (sec.get("context") or {}).get("displayName", "")

        if not context:
            result[key] = content
        else:
            if key not in result or isinstance(result[key], str):
                result[key] = {}
            result[key][context] = content

    return result

def cmd_rule(opts):
    rule_key = opts.get("key")
    if not rule_key:
        fail("MISSING_PARAM", "Use: sonar.py rule --key csharpsquid:S6966")

    token = load_token()
    if not token:
        fail("TOKEN_NOT_FOUND")

    project_key = opts.get("project") or detect_repo()
    if project_key:
        resolved, _ = resolve_project_key(project_key, None, token)
        project_key = resolved

    org = opts.get("org") or detect_org(project_key, token)

    sys.stderr.write(f"rule | key={rule_key} org={org or '(none)'}\n")

    params = {"key": rule_key}
    if org:
        params["organization"] = org

    data, api_err = api_get("rules/show", params, token)
    if api_err:
        fail("FETCH_FAILED", f"rules/show: HTTP {api_err['code']}: {api_err['message']}")

    r = data.get("rule", data)
    result = {
        "key": r.get("key"),
        "name": r.get("name"),
        "severity": r.get("severity"),
        "type": r.get("type"),
        "lang": r.get("lang"),
        "langName": r.get("langName"),
        "description": r.get("mdDesc") or r.get("htmlDesc") or r.get("description"),
        "sections": _parse_description_sections(r.get("descriptionSections") or []),
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


# ──────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────

COMMANDS = {
    "health": cmd_health,
    "issues": cmd_issues,
    "files": cmd_files,
    "rule": cmd_rule,
}


def parse_args(argv):
    opts = {}
    i = 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            opts[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            i += 1
    return opts


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        subcmd = "health"
        opts = parse_args(sys.argv[1:])
    else:
        subcmd = sys.argv[1]
        opts = parse_args(sys.argv[2:])

    handler = COMMANDS.get(subcmd)
    if not handler:
        cmds = ", ".join(COMMANDS.keys())
        fail("UNKNOWN_COMMAND", f"'{subcmd}' nao reconhecido. Disponiveis: {cmds}")

    handler(opts)


if __name__ == "__main__":
    main()
