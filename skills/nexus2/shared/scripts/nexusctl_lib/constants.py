STATUSES = ("READY", "ACTIVE", "QA", "DONE", "BLOCKED")

TASK_MARKERS = {" ": "pending", ">": "in_progress", "x": "completed", "!": "failed"}
REVERSE_TASK_MARKERS = {value: key for key, value in TASK_MARKERS.items()}

DEFAULT_LEASE_MINUTES = 45

DEFAULT_BANNED_FOLDERS = {
    "Data",
    "Database",
    "Network",
    "Http",
    "Util",
    "Common",
    "Models",
    "Dto",
    "Core",
}

AUDIT_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".temp",
    ".nexus",
    "nexus",
    "node_modules",
    "bin",
    "obj",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
}

FRONTMATTER_ORDER = [
    "id",
    "status",
    "title",
    "complexity",
    "priority",
    "owner",
    "claimed_at",
    "heartbeat_at",
    "lease_until",
    "current_task",
    "write_scope",
]
