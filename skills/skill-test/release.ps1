# release.ps1 — thin wrapper; all logic lives in scripts/build_release.py.
# Builds an installable copy of this skill in release/skill-test/ (excludes
# README.md, this skill's own dogfood tests/, and caches — see the script's
# docstring for the exact rules).
$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
python "$scriptDir/scripts/build_release.py" @args
