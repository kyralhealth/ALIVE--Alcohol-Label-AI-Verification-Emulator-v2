"""Demo mode: canned extractions for the bundled sample labels.

Lets reviewers exercise the full UI + verification engine without an Anthropic
API key (LABEL_DEMO=1). Keyed by uploaded filename; unknown files get a clear
error pointing at the samples directory.
"""
from typing import Optional

from .comparison import GOVERNMENT_WARNING_TEXT
from .schemas import ExtractedLabel

_BAD_WARNING = (
    "Government Warning: (1) According to the Surgeon General, women should not "
    "consume alcoholic beverages during pregnancy because of the risk of birth "
    "defects. (2) Consumption of alcoholic beverages impairs your ability to "
    "drive a car or operate machinery."
)

DEMO_EXTRACTIONS = {
    "old_tom_bourbon.png": ExtractedLabel(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=GOVERNMENT_WARNING_TEXT,
        warning_prefix_verbatim="GOVERNMENT WARNING:",
        warning_appears_bold="yes",
        image_legibility="good",
    ),
    "stones_throw_gin.png": ExtractedLabel(
        brand_name="STONE'S THROW",
        class_type="London Dry Gin",
        alcohol_content="47% ALC/VOL",
        net_contents="750 mL",
        government_warning=GOVERNMENT_WARNING_TEXT,
        warning_prefix_verbatim="GOVERNMENT WARNING:",
        warning_appears_bold="yes",
        image_legibility="good",
    ),
    "harbor_light_vodka.png": ExtractedLabel(
        brand_name="HARBOR LIGHT",
        class_type="Vodka",
        alcohol_content="40% Alc./Vol. (80 Proof)",
        net_contents="1 L",
        government_warning=_BAD_WARNING,
        warning_prefix_verbatim="Government Warning:",
        warning_appears_bold="no",
        image_legibility="good",
    ),
    "ridge_runner_rye.png": ExtractedLabel(
        brand_name="RIDGE RUNNER",
        class_type="Straight Rye Whiskey",
        alcohol_content="43% Alc./Vol. (86 Proof)",
        net_contents="750 mL",
        government_warning=GOVERNMENT_WARNING_TEXT,
        warning_prefix_verbatim="GOVERNMENT WARNING:",
        warning_appears_bold="unclear",
        image_legibility="good",
    ),
}


class DemoExtractor:
    """Drop-in replacement for Extractor that never calls the API."""

    model = "demo"
    available = True

    async def extract(self, image_bytes: bytes, filename: Optional[str] = None) -> ExtractedLabel:
        if filename and filename in DEMO_EXTRACTIONS:
            return DEMO_EXTRACTIONS[filename]
        raise RuntimeError(
            "Demo mode only recognizes the bundled sample labels ({}). "
            "Set ANTHROPIC_API_KEY and unset LABEL_DEMO to verify arbitrary images.".format(
                ", ".join(sorted(DEMO_EXTRACTIONS)))
        )
