"""Re-center panelist gold rings inside their square source images.

Why this exists
---------------
The briefing renders each bust avatar from a square blob asset (`{key}.png`) with
a single email-safe rule: ``border-radius:50%`` on the ``<img>`` (see
``src/output/briefing_style.py::portrait_clip_styles``). That clip is the circle
*inscribed in the square*, centered on the square. If the baked-in gold ring is
not concentric with the square, the clip shaves one edge of the ring and leaves a
dark crescent of background on the opposite edge — the avatar looks "off" in the
circular hole.

We cannot fix this with CSS: ``object-fit`` / ``object-position`` are stripped by
Gmail/Outlook and are a hard Graphics-QA fail (``docs/briefing_style.py`` mandate,
``src/qa/visual_audit.py``). So we fix the *asset*: detect the gold ring, crop a
square centered on the ring, and re-export. After this, ``border-radius:50%``
lands flush on the frame with no recrop needed in the template.

Usage
-----
    .venv\\Scripts\\python.exe scripts\\recenter_avatars.py \\
        --src "<dir with *hypatia-*.png ...>" --out assets/avatars [--proof]

Output is written as ``{key}.png`` ready to upload to the blob container:
    az storage blob upload-batch -d assets -s assets/avatars --account-name stboardroomprod --overwrite
"""

from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path

from PIL import Image, ImageDraw

# Roster keys — keep in sync with src/core/board_roster.py::PANELIST_KEYS.
PANELIST_KEYS = ("hypatia", "davinci", "suntzu", "tesla", "aurelius")

# SoTU row background per panelist stance (from briefing_style SOTU_*_BG) — proof only.
PROOF_CARD_BG = {
    "hypatia": (59, 10, 10),    # bearish  #3b0a0a
    "davinci": (5, 46, 36),     # bullish  #052e24
    "suntzu": (5, 46, 36),      # bullish  #052e24
    "tesla": (5, 46, 36),       # bullish  #052e24
    "aurelius": (59, 10, 10),   # bearish  #3b0a0a
}


def find_source(src_dir: str, key: str) -> str | None:
    """Newest source PNG matching the panelist key (handles cursor asset hashes)."""
    matches = sorted(
        glob.glob(os.path.join(src_dir, f"*{key}*.png")),
        key=os.path.getmtime,
        reverse=True,
    )
    return matches[0] if matches else None


def gold_ring_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    """Bounding box of the outermost gold-frame pixels (warm, bright, R>=G>B)."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    minx, miny, maxx, maxy = w, h, 0, 0
    found = False
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if r > 150 and g > 105 and b < 130 and r >= g >= b and (r - b) > 50:
                found = True
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y
    if not found:
        raise ValueError("no gold-ring pixels detected")
    return minx, miny, maxx, maxy


def recenter(img: Image.Image, *, out_size: int = 1024, pad_frac: float = 0.0) -> Image.Image:
    """Crop a square centered on the gold ring so the ring is concentric.

    ``pad_frac`` adds a uniform transparent margin (fraction of ring diameter) so
    the circular clip never shaves the outermost gold pixel. 0.0 == flush.
    """
    minx, miny, maxx, maxy = gold_ring_bbox(img)
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0
    diameter = max(maxx - minx, maxy - miny)
    half = (diameter / 2.0) * (1.0 + pad_frac)

    src = img.convert("RGBA")
    left, top = int(round(cx - half)), int(round(cy - half))
    right, bottom = int(round(cx + half)), int(round(cy + half))
    side = right - left
    # Transparent canvas so any out-of-bounds margin is clear, not grey.
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(src.crop((left, top, right, bottom)), (0, 0))
    return canvas.resize((out_size, out_size), Image.LANCZOS)


def _circle_clip(img: Image.Image, size: int, bg: tuple[int, int, int]) -> Image.Image:
    """Render a thumbnail with border-radius:50% on the given card background (proof)."""
    thumb = img.convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    card = Image.new("RGBA", (size, size), bg + (255,))
    card.paste(thumb, (0, 0), mask)
    return card


def build_proof(src_dir: str, out_dir: str, fixed: dict[str, Image.Image]) -> str:
    """Side-by-side before/after of the real circular clip on real card colors."""
    size, gap, pad = 128, 24, 20
    cols = len(PANELIST_KEYS)
    label = 26
    grid_w = pad * 2 + cols * size + (cols - 1) * gap
    grid_h = pad * 2 + label + 2 * (size + label) + gap
    proof = Image.new("RGBA", (grid_w, grid_h), (18, 18, 18, 255))
    draw = ImageDraw.Draw(proof)
    draw.text((pad, 6), "BEFORE (shipped)", fill=(252, 165, 165, 255))
    after_y = pad + label + size + label + gap
    draw.text((pad, after_y - label + 4), "AFTER (recentered)", fill=(110, 231, 183, 255))
    for i, key in enumerate(PANELIST_KEYS):
        bg = PROOF_CARD_BG[key]
        x = pad + i * (size + gap)
        before_src = find_source(src_dir, key)
        if before_src:
            proof.alpha_composite(_circle_clip(Image.open(before_src), size, bg), (x, pad + label))
        proof.alpha_composite(_circle_clip(fixed[key], size, bg), (x, after_y))
        draw.text((x, pad + label + size + 2), key, fill=(161, 161, 170, 255))
    out = os.path.join(out_dir, "_recenter_proof.png")
    proof.convert("RGB").save(out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Re-center panelist gold rings.")
    ap.add_argument("--src", required=True, help="Directory holding source PNGs.")
    ap.add_argument("--out", default="assets/avatars", help="Output directory.")
    ap.add_argument("--pad-frac", type=float, default=0.0, help="Uniform margin (fraction of ring dia).")
    ap.add_argument("--proof", action="store_true", help="Also write _recenter_proof.png.")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    fixed: dict[str, Image.Image] = {}
    for key in PANELIST_KEYS:
        src = find_source(args.src, key)
        if not src:
            print(f"  [skip] {key}: no source found in {args.src}")
            continue
        img = Image.open(src)
        out_img = recenter(img, pad_frac=args.pad_frac)
        fixed[key] = out_img
        out_img.save(out_dir / f"{key}.png")
        print(f"  [ok]   {key}: {os.path.basename(src)} -> {out_dir / f'{key}.png'}")

    if args.proof and fixed:
        proof = build_proof(args.src, str(out_dir), fixed)
        print(f"  [proof] {proof}")


if __name__ == "__main__":
    main()
