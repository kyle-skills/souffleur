#!/usr/bin/env python3
"""
Souffleur: Recovery Configuration Resolver

Resolves compact-threshold and max-permission settings from
.orchestra_configs/souffleur files.

Search order (first hit wins):
1. <project-dir>/.orchestra_configs/souffleur
2. <project-dir>/../.orchestra_configs/souffleur

Output is always valid JSON. Invalid or missing values emit warnings and
fallback to safe defaults.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_FORCE_COMPACT = 400000
DEFAULT_MAX_EXTERNAL_PERMISSION = "acceptEdits"
ALLOWED_PERMISSIONS = {"acceptEdits", "bypassPermissions"}


def _find_config_file(project_dir: Path) -> Path | None:
    candidates = [
        project_dir / ".orchestra_configs" / "souffleur",
        project_dir.parent / ".orchestra_configs" / "souffleur",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _parse_config(path: Path) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    warnings: list[str] = []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        warnings.append(f"Unable to read config file {path}: {exc}")
        return values, warnings

    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            warnings.append(
                f"Ignoring malformed config line {line_no} in {path} (missing '=')"
            )
            continue

        key, value = line.split("=", 1)

        # Preserve strict key matching while still tolerating accidental spaces.
        key = key.strip()
        value = value.strip()

        if key in values:
            warnings.append(f"Duplicate key '{key}' on line {line_no} in {path}; last value wins")

        values[key] = value

    return values, warnings


def _resolve(project_dir: Path) -> dict:
    warnings: list[str] = []
    config_path = _find_config_file(project_dir)

    source = None
    raw: dict[str, str] = {}
    if config_path is not None:
        source = str(config_path)
        raw, parse_warnings = _parse_config(config_path)
        warnings.extend(parse_warnings)

    # FORCE_COMPACT
    force_compact = DEFAULT_FORCE_COMPACT
    raw_force = raw.get("FORCE_COMPACT")
    if raw_force is not None:
        try:
            parsed = int(raw_force)
            if parsed > 0:
                force_compact = parsed
            else:
                warnings.append(
                    f"Invalid FORCE_COMPACT='{raw_force}' (must be positive integer); using default {DEFAULT_FORCE_COMPACT}"
                )
        except ValueError:
            warnings.append(
                f"Invalid FORCE_COMPACT='{raw_force}' (must be positive integer); using default {DEFAULT_FORCE_COMPACT}"
            )

    # MAX_EXTERNAL_PERMISSION
    max_external_permission = DEFAULT_MAX_EXTERNAL_PERMISSION
    raw_max_perm = raw.get("MAX_EXTERNAL_PERMISSION")
    if raw_max_perm is not None:
        if raw_max_perm in ALLOWED_PERMISSIONS:
            max_external_permission = raw_max_perm
        else:
            warnings.append(
                f"Invalid MAX_EXTERNAL_PERMISSION='{raw_max_perm}' (allowed: acceptEdits|bypassPermissions); using default {DEFAULT_MAX_EXTERNAL_PERMISSION}"
            )

    # Warn on unknown keys to reduce silent config drift.
    known = {"FORCE_COMPACT", "MAX_EXTERNAL_PERMISSION"}
    for key in raw:
        if key not in known:
            warnings.append(f"Ignoring unknown config key '{key}'")

    return {
        "force_compact_threshold_tokens": force_compact,
        "max_external_permission": max_external_permission,
        "source": source,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Souffleur config resolver")
    parser.add_argument(
        "--project-dir",
        default=".",
        help="Project directory for .orchestra_configs lookup (default: current directory)",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    result = _resolve(project_dir)

    for warning in result["warnings"]:
        print(f"Warning: {warning}", file=sys.stderr)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
