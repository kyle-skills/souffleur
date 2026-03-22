#!/usr/bin/env python3
"""
Souffleur: Export Context Estimator

Estimates effective token load from a claude_export markdown artifact.

Scope rule:
- If compact marker(s) are present, estimate only from the latest marker onward.
- If no marker is found, estimate from the start of file.

Token estimate is conservative: chars / 3.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DIVISOR = 3

# Markers chosen to cover known compact evidence in exported markdown.
MARKER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"compact_boundary", re.IGNORECASE),
    re.compile(r"(^|\n)\s*/compact\b", re.IGNORECASE),
    re.compile(r"Compacted\s*\(", re.IGNORECASE),
    re.compile(r"\[lethe summary\]", re.IGNORECASE),
    re.compile(r"microcompact_boundary", re.IGNORECASE),
]


def _find_marker_offsets(content: str) -> list[tuple[int, int, str]]:
    hits: list[tuple[int, int, str]] = []
    for pattern in MARKER_PATTERNS:
        for match in pattern.finditer(content):
            hits.append((match.start(), match.end(), pattern.pattern))
    hits.sort(key=lambda item: (item[0], item[1]))
    return hits


def _estimate(content: str) -> dict:
    full_chars = len(content)
    full_tokens = full_chars // DIVISOR

    markers = _find_marker_offsets(content)
    if markers:
        start_offset = markers[-1][1]
        scope_mode = "last_compact_marker"
        marker_found = True
    else:
        start_offset = 0
        scope_mode = "full_file"
        marker_found = False

    scoped_content = content[start_offset:]
    scoped_chars = len(scoped_content)
    scoped_tokens = scoped_chars // DIVISOR

    return {
        "ok": True,
        "estimated_tokens": scoped_tokens,
        "estimated_tokens_full": full_tokens,
        "chars_scoped": scoped_chars,
        "chars_full": full_chars,
        "start_mode": scope_mode,
        "start_offset": start_offset,
        "marker_found": marker_found,
        "marker_count": len(markers),
        "warnings": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Estimate effective tokens from claude_export artifact")
    parser.add_argument("export_path", help="Absolute or relative path to trimmed export markdown")
    args = parser.parse_args()

    export_path = Path(args.export_path).expanduser().resolve()
    if not export_path.is_file():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Export file not found: {export_path}",
                    "warnings": [],
                },
                indent=2,
            )
        )
        return 2

    try:
        content = export_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Unable to read export file: {exc}",
                    "warnings": [],
                },
                indent=2,
            )
        )
        return 3

    result = _estimate(content)
    result["source"] = str(export_path)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
