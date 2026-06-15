"""Generate sample label PNGs + applications.csv for testing and demo mode.

The four labels exercise the interesting cases from the discovery interviews:
  old_tom_bourbon    - everything matches (the spec's example label)
  stones_throw_gin   - brand caps differ from the application (Dave's example)
  harbor_light_vodka - warning in title case, reworded, not bold -> reject
  ridge_runner_rye   - ABV on label differs from application -> reject
Run:  .venv/bin/python scripts/generate_samples.py
"""
import csv
import os
import sys
import textwrap

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.comparison import GOVERNMENT_WARNING_TEXT  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "samples")

FONT_CANDIDATES = {
    "bold": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
             "/Library/Fonts/Arial Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "regular": ["/System/Library/Fonts/Supplemental/Arial.ttf",
                "/Library/Fonts/Arial.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "serif": ["/System/Library/Fonts/Supplemental/Georgia.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"],
}


def font(kind, size):
    for path in FONT_CANDIDATES[kind]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


BAD_WARNING = (
    "Government Warning: (1) According to the Surgeon General, women should not "
    "consume alcoholic beverages during pregnancy because of the risk of birth "
    "defects. (2) Consumption of alcoholic beverages impairs your ability to "
    "drive a car or operate machinery."
)

LABELS = [
    {
        "file": "old_tom_bourbon.png", "bg": "#f3ead8", "fg": "#2b1d0e", "accent": "#7a1f1f",
        "brand": "OLD TOM DISTILLERY", "type": "Kentucky Straight Bourbon Whiskey",
        "abv": "45% Alc./Vol. (90 Proof)", "net": "750 mL",
        "warning": GOVERNMENT_WARNING_TEXT, "warning_bold_prefix": True,
    },
    {
        "file": "stones_throw_gin.png", "bg": "#e8f0ec", "fg": "#11302a", "accent": "#1f6e5d",
        "brand": "STONE'S THROW", "type": "London Dry Gin",
        "abv": "47% ALC/VOL", "net": "750 mL",
        "warning": GOVERNMENT_WARNING_TEXT, "warning_bold_prefix": True,
    },
    {
        "file": "harbor_light_vodka.png", "bg": "#eef1f6", "fg": "#15243d", "accent": "#27518f",
        "brand": "HARBOR LIGHT", "type": "Vodka",
        "abv": "40% Alc./Vol. (80 Proof)", "net": "1 L",
        "warning": BAD_WARNING, "warning_bold_prefix": False,
    },
    {
        "file": "ridge_runner_rye.png", "bg": "#f5e9dc", "fg": "#33210f", "accent": "#8a5a18",
        "brand": "RIDGE RUNNER", "type": "Straight Rye Whiskey",
        "abv": "43% Alc./Vol. (86 Proof)", "net": "750 mL",
        "warning": GOVERNMENT_WARNING_TEXT, "warning_bold_prefix": True,
    },
]

# What the (sometimes mismatching) COLA application says for each label.
APPLICATIONS = [
    ["old_tom_bourbon.png", "OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey",
     "45% Alc./Vol. (90 Proof)", "750 mL"],
    ["stones_throw_gin.png", "Stone's Throw", "London Dry Gin", "47% Alc./Vol.", "750 mL"],
    ["harbor_light_vodka.png", "HARBOR LIGHT", "Vodka", "40% Alc./Vol.", "1 L"],
    ["ridge_runner_rye.png", "RIDGE RUNNER", "Straight Rye Whiskey",
     "45% Alc./Vol. (90 Proof)", "750 mL"],
]


def draw_label(spec):
    W, H = 1000, 1400
    img = Image.new("RGB", (W, H), spec["bg"])
    d = ImageDraw.Draw(img)
    d.rectangle([30, 30, W - 30, H - 30], outline=spec["accent"], width=6)
    d.rectangle([46, 46, W - 46, H - 46], outline=spec["accent"], width=2)

    y = 150
    for line in textwrap.wrap(spec["brand"], 14):
        f = font("serif", 92)
        w = d.textlength(line, font=f)
        d.text(((W - w) / 2, y), line, font=f, fill=spec["fg"])
        y += 110
    y += 30
    f = font("regular", 46)
    for line in textwrap.wrap(spec["type"], 30):
        w = d.textlength(line, font=f)
        d.text(((W - w) / 2, y), line, font=f, fill=spec["accent"])
        y += 60
    y += 50
    d.line([(W * 0.25, y), (W * 0.75, y)], fill=spec["accent"], width=3)
    y += 50
    f = font("bold", 44)
    for text in (spec["abv"], spec["net"]):
        w = d.textlength(text, font=f)
        d.text(((W - w) / 2, y), text, font=f, fill=spec["fg"])
        y += 70

    # Government warning block near the bottom.
    y = H - 360
    warning = spec["warning"]
    prefix_end = warning.index(":") + 1
    prefix, body = warning[:prefix_end], warning[prefix_end:].strip()
    f_prefix = font("bold" if spec["warning_bold_prefix"] else "regular", 30)
    f_body = font("regular", 30)
    d.text((80, y), prefix, font=f_prefix, fill=spec["fg"])
    y += 44
    for line in textwrap.wrap(body, 60):
        d.text((80, y), line, font=f_body, fill=spec["fg"])
        y += 40

    img.save(os.path.join(OUT, spec["file"]))
    print("wrote", spec["file"])


def main():
    os.makedirs(OUT, exist_ok=True)
    for spec in LABELS:
        draw_label(spec)
    csv_path = os.path.join(OUT, "applications.csv")
    with open(csv_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["filename", "brand_name", "class_type", "alcohol_content", "net_contents"])
        writer.writerows(APPLICATIONS)
    print("wrote applications.csv")


if __name__ == "__main__":
    main()
