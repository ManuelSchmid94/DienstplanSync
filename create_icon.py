"""
Run once to generate assets/icon.icns from scratch.
Requires Pillow: pip install Pillow
macOS only (uses iconutil).
"""
import os
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow nicht installiert. Bitte: pip install Pillow")
    sys.exit(1)

ICONSET = Path("assets/AppIcon.iconset")
ICONSET.mkdir(parents=True, exist_ok=True)

BG_COLOR = (14, 99, 156, 255)    # VSCode-blue
FG_COLOR = (255, 255, 255, 255)

SIZES = [16, 32, 64, 128, 256, 512, 1024]


def make_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), BG_COLOR)
    d = ImageDraw.Draw(img)

    # Rounded rect effect via inner gradient circle
    cx, cy, r = size / 2, size / 2, size * 0.42
    for px in range(size):
        for py in range(size):
            dist = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
            if dist > r * 1.05:
                img.putpixel((px, py), (0, 0, 0, 0))  # transparent corners

    # Letter "D"
    font_size = max(int(size * 0.52), 8)
    font = None
    for font_path in [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
    ]:
        if Path(font_path).exists():
            try:
                font = ImageFont.truetype(font_path, font_size)
                break
            except Exception:
                continue

    if font is None:
        font = ImageFont.load_default()

    text = "DS"
    bbox = d.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (size - tw) / 2 - bbox[0]
    y = (size - th) / 2 - bbox[1]
    d.text((x, y), text, fill=FG_COLOR, font=font)
    return img


for sz in SIZES:
    icon = make_icon(sz)
    icon.save(ICONSET / f"icon_{sz}x{sz}.png")
    if sz <= 512:
        big = make_icon(sz * 2)
        big.save(ICONSET / f"icon_{sz}x{sz}@2x.png")
    print(f"  {sz}×{sz} ✓")

result = subprocess.run(
    ["iconutil", "-c", "icns", str(ICONSET), "-o", "assets/icon.icns"],
    capture_output=True, text=True,
)
if result.returncode != 0:
    print("iconutil-Fehler:", result.stderr)
    sys.exit(1)

import shutil
shutil.rmtree(ICONSET)
print("\nassets/icon.icns erstellt.")
