#!/usr/bin/env python3
"""Generate ``translations/en.json`` from ``strings.json``.

Home Assistant resolves ``[%key:...%]`` back-references when it builds core, but
custom integrations ship their translations as-is. This script does that
resolution so ``strings.json`` can stay free of duplicated wording.

Usage: ``python scripts/build_translations.py [--check]``
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

COMPONENT = "maintenance_tracker"
ROOT = Path(__file__).resolve().parent.parent
COMPONENT_DIR = ROOT / "custom_components" / COMPONENT
STRINGS = COMPONENT_DIR / "strings.json"
TARGET = COMPONENT_DIR / "translations" / "en.json"

REFERENCE = re.compile(r"^\[%key:(?P<path>[^%]+)%\]$")

#: The handful of `common::` keys used, mirrored from core's shared strings.
COMMON: dict[str, str] = {
    "common::config_flow::data::name": "Name",
    "common::config_flow::abort::already_configured_device": (
        "Device is already configured"
    ),
    "common::config_flow::abort::reconfigure_successful": (
        "Re-configuration was successful"
    ),
}


def _lookup(data: dict[str, Any], path: str) -> str:
    """Resolve a ``component::domain::a::b`` path inside the strings tree."""
    if path in COMMON:
        return COMMON[path]

    parts = path.split("::")
    if parts[:2] != ["component", COMPONENT]:
        raise KeyError(f"Unsupported reference: {path}")

    node: Any = data
    for part in parts[2:]:
        node = node[part]
    if not isinstance(node, str):
        raise TypeError(f"Reference {path} does not point at a string")
    return node


def resolve(node: Any, root: dict[str, Any], seen: int = 0) -> Any:
    """Recursively replace every back-reference with its target string."""
    if seen > 10:
        raise RecursionError("Reference chain too deep; is there a cycle?")

    if isinstance(node, dict):
        return {key: resolve(value, root, seen) for key, value in node.items()}
    if isinstance(node, list):
        return [resolve(value, root, seen) for value in node]
    if isinstance(node, str) and (match := REFERENCE.match(node)):
        return resolve(_lookup(root, match["path"]), root, seen + 1)
    return node


def main() -> int:
    """Build the file, or verify it is up to date."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the generated file is out of date",
    )
    args = parser.parse_args()

    strings = json.loads(STRINGS.read_text(encoding="utf-8"))
    rendered = (
        json.dumps(resolve(strings, strings), indent=2, ensure_ascii=False) + "\n"
    )

    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != rendered:
            print(f"{TARGET.relative_to(ROOT)} is out of date; run this script.")
            return 1
        print(f"{TARGET.relative_to(ROOT)} is up to date.")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(rendered, encoding="utf-8")
    print(f"Wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
