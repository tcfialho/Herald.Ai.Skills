#!/usr/bin/env python3
"""Small provider boundary: core metrics, evidence and acceptance are agent-agnostic."""

import json
import os
from pathlib import Path
import shutil


SKILL_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_WORKER_TOOLS = ('Read', 'Bash(python3 *)', 'Bash(python *)',
                       'Bash(git status*)', 'Bash(git diff*)', 'Bash(git log*)')


class AdapterError(Exception):
    pass


def resolve_provider(requested, custom=None):
    if requested != 'auto':
        return requested
    if custom:
        return 'command'
    if os.environ.get('CLAUDECODE') and shutil.which('claude'):
        return 'claude'
    if os.environ.get('CODEX_HOME') and shutil.which('codex'):
        return 'codex'
    for provider in ('codex', 'claude'):
        if shutil.which(provider):
            return provider
    raise AdapterError('no supported agent CLI; configure an explicit argv adapter')


def worker_command(provider, workspace, executable=None, model=None, custom=None, claude_permission_mode=None):
    workspace = str(Path(workspace).resolve())
    if provider == 'codex':
        binary = executable or 'codex'
        cmd = [binary, 'exec', '--json', '-C', workspace]
        if model:
            cmd += ['--model', model]
        return cmd + ['-']
    if provider == 'claude':
        binary = executable or 'claude'
        cmd = [binary, '-p', '--output-format', 'stream-json', '--verbose']
        if claude_permission_mode is not None:
            if claude_permission_mode not in ('acceptEdits', 'bypassPermissions', 'default', 'plan'):
                raise AdapterError('unsupported Claude permission mode')
            cmd += ['--permission-mode', claude_permission_mode]
        # Headless -p denies reads outside the workspace and all Bash; the worker
        # must read this skill and run loop_guard.py plus its own Python checks.
        cmd += ['--add-dir', str(SKILL_ROOT), '--allowedTools', ','.join(CLAUDE_WORKER_TOOLS)]
        if model:
            cmd += ['--model', model]
        return cmd
    if provider == 'command':
        if not custom or not isinstance(custom, list) or not all(isinstance(x, str) and x for x in custom):
            raise AdapterError('AGY or another CLI needs an explicit argv configuration')
        return [part.replace('{workspace}', workspace) for part in custom]
    raise AdapterError(f'unsupported provider: {provider}')


def executable_available(provider, executable=None, custom=None):
    try:
        cmd = worker_command(provider, '/', executable=executable, custom=custom)
    except AdapterError:
        return False
    first = cmd[0]
    return bool(shutil.which(first) or Path(first).is_file())
