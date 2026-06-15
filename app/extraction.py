"""Label OCR/extraction via Claude vision.

The model's only job is transcription: read the label and return the raw text
of each field, preserving capitalization exactly. All pass/fail logic lives in
comparison.py. Structured outputs (output_config.format) guarantee the
response parses.
"""
import base64
import io
import json
import os
from typing import Optional, Tuple

import anthropic
from PIL import Image

from .schemas import ExtractedLabel

# Haiku is the deliberate default: the TTB requirement is results in ~5 seconds
# or agents go back to checking by eye. Override with LABEL_MODEL (e.g.
# claude-opus-4-8) if accuracy on difficult artwork matters more than latency.
DEFAULT_MODEL = "claude-haiku-4-5"

MAX_IMAGE_EDGE = 1568  # px — bigger buys no accuracy at typical label sizes, just latency

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "brand_name": {"type": ["string", "null"], "description": "Brand name exactly as printed, preserving capitalization."},
        "class_type": {"type": ["string", "null"], "description": "Class/type designation, e.g. 'Kentucky Straight Bourbon Whiskey'."},
        "alcohol_content": {"type": ["string", "null"], "description": "Alcohol content statement verbatim, e.g. '45% Alc./Vol. (90 Proof)'."},
        "net_contents": {"type": ["string", "null"], "description": "Net contents verbatim, e.g. '750 mL'."},
        "government_warning": {"type": ["string", "null"], "description": "The full government health warning statement, transcribed verbatim including the lead-in, preserving capitalization exactly."},
        "warning_prefix_verbatim": {"type": ["string", "null"], "description": "The first two words of the warning plus colon, exactly as printed (e.g. 'GOVERNMENT WARNING:' or 'Government Warning:')."},
        "warning_appears_bold": {"type": "string", "enum": ["yes", "no", "unclear"], "description": "Whether the warning lead-in appears to be in bold type."},
        "image_legibility": {"type": "string", "enum": ["good", "poor"], "description": "'poor' if glare, blur, angle, or low resolution made any field hard to read."},
        "legibility_notes": {"type": ["string", "null"], "description": "Short note on any legibility problems, else null."},
    },
    "required": [
        "brand_name", "class_type", "alcohol_content", "net_contents",
        "government_warning", "warning_prefix_verbatim", "warning_appears_bold",
        "image_legibility", "legibility_notes",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You transcribe alcohol beverage label artwork for TTB compliance review. "
    "Read the supplied label image and return every requested field VERBATIM, "
    "preserving capitalization, punctuation, and spacing exactly as printed. "
    "Do not correct, normalize, or complete text — if a word is misspelled on "
    "the label, transcribe the misspelling. Use null for anything not present "
    "or unreadable. The image may be photographed at an angle or have glare; "
    "do your best and report legibility honestly."
)


def prepare_image(data: bytes) -> Tuple[str, str]:
    """Re-encode the upload as a bounded-size PNG; returns (base64, media_type).

    Downscaling keeps requests fast (the 5-second budget) and normalizes exotic
    formats (HEIC fails here and surfaces a clear error instead of a 400 from
    the API).
    """
    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")
    except Exception:
        raise ValueError(
            "Could not read the uploaded file as an image. Please upload a "
            "JPEG or PNG of the label.")
    long_edge = max(img.size)
    if long_edge > MAX_IMAGE_EDGE:
        scale = MAX_IMAGE_EDGE / long_edge
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.standard_b64encode(buf.getvalue()).decode("ascii"), "image/png"


class Extractor:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.model = model or os.environ.get("LABEL_MODEL", DEFAULT_MODEL)
        self._client = anthropic.AsyncAnthropic(api_key=api_key) if (
            api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        ) else None

    @property
    def available(self) -> bool:
        return self._client is not None

    async def extract(self, image_bytes: bytes, filename: Optional[str] = None) -> ExtractedLabel:
        if self._client is None:
            raise RuntimeError(
                "No Anthropic API key configured. Set ANTHROPIC_API_KEY, or run "
                "with LABEL_DEMO=1 to try the app with the bundled sample labels."
            )
        b64, media_type = prepare_image(image_bytes)
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            output_config={"format": {"type": "json_schema", "schema": EXTRACTION_SCHEMA}},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text",
                     "text": "Transcribe the label fields as specified."},
                ],
            }],
        )
        text = next(b.text for b in response.content if b.type == "text")
        return ExtractedLabel(**json.loads(text))
