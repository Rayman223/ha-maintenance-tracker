#!/usr/bin/env python3
"""Generate the brand assets HACS looks for.

Draws a gauge whose needle has swung into the warning zone — the whole point of
the integration, readable down to a 32 px tab icon. Keeping the icon generated
rather than hand-drawn means it can be regenerated at any size, and reviewed as
a diff instead of an opaque binary.

Usage: ``python scripts/build_brand_assets.py``
Requires Pillow (``pip install pillow``), which is a dev-only dependency.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BRAND_DIR = ROOT / "custom_components" / "maintenance_tracker" / "brand"

#: Home Assistant blue, the warning amber the card uses, and white.
BACKGROUND = (3, 169, 244, 255)
DIAL = (255, 255, 255, 255)
WARNING = (255, 166, 0, 255)

#: Drawn this many times larger, then reduced — Pillow's arcs are not antialiased.
SUPERSAMPLE = 8

#: The dial sweeps clockwise from lower left to lower right, 0 degrees at 3 o'clock.
DIAL_START = 160
DIAL_END = 380
WARNING_START = 330
NEEDLE_ANGLE = 348


def _draw(size: int) -> Image.Image:
    """Draw the icon at the requested size."""
    scale = size * SUPERSAMPLE
    image = Image.new("RGBA", (scale, scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (0, 0, scale - 1, scale - 1), radius=scale * 0.22, fill=BACKGROUND
    )

    inset = scale * 0.26
    box = (inset, inset, scale - inset, scale - inset)
    thickness = int(scale * 0.085)

    draw.arc(box, DIAL_START, DIAL_END, fill=DIAL, width=thickness)
    draw.arc(box, WARNING_START, DIAL_END, fill=WARNING, width=thickness)

    # The needle points into the warning arc: maintenance is due.
    centre = scale / 2
    length = scale * 0.235
    radians = math.radians(NEEDLE_ANGLE)
    draw.line(
        (
            centre,
            centre,
            centre + length * math.cos(radians),
            centre + length * math.sin(radians),
        ),
        fill=DIAL,
        width=int(scale * 0.062),
    )

    pivot = scale * 0.052
    draw.ellipse(
        (centre - pivot, centre - pivot, centre + pivot, centre + pivot), fill=DIAL
    )

    return image.resize((size, size), Image.LANCZOS)


def main() -> int:
    """Write icon.png and icon@2x.png."""
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    for size, name in ((256, "icon.png"), (512, "icon@2x.png")):
        target = BRAND_DIR / name
        _draw(size).save(target, "PNG", optimize=True)
        print(f"Wrote {target.relative_to(ROOT)} ({size}x{size})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
