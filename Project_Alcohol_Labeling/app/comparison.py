"""Deterministic verification engine.

Claude only *reads* the label; every compliance verdict is produced here by
plain, testable Python so the rules are auditable and never drift with model
behavior.

Statuses per field:
  match     - agent doesn't need to look at it
  review    - probably fine, but a human should glance (e.g. case differences)
  mismatch  - the values disagree
  missing   - required on the label but not found
Overall: pass (all match) / review (no mismatch, some review) / fail.
"""
import difflib
import re
import unicodedata
from typing import List, Optional, Tuple

from .schemas import ApplicationData, ExtractedLabel, FieldResult, VerificationResult

# 27 CFR Part 16 — must appear verbatim on every alcohol beverage label.
GOVERNMENT_WARNING_TEXT = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth "
    "defects. (2) Consumption of alcoholic beverages impairs your ability to "
    "drive a car or operate machinery, and may cause health problems."
)

_QUOTE_MAP = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", " ": " ",
}


def _clean(text: str) -> str:
    """Unicode-normalize, map smart quotes, collapse whitespace."""
    text = unicodedata.normalize("NFKC", text)
    for src, dst in _QUOTE_MAP.items():
        text = text.replace(src, dst)
    return re.sub(r"\s+", " ", text).strip()


def _loose(text: str) -> str:
    """Lowercase and strip punctuation for fuzzy comparison."""
    return re.sub(r"[^a-z0-9 ]", "", _clean(text).lower()).strip()


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _loose(a), _loose(b)).ratio()


# ---------------------------------------------------------------- text fields

def compare_text_field(field: str, label_value: Optional[str], app_value: str) -> FieldResult:
    """Brand name / class-type comparison with tiered judgment.

    Exact -> match; differs only by case/punctuation/spacing -> match with a
    note (Dave's STONE'S THROW vs Stone's Throw case); close but not identical
    -> review; otherwise mismatch.
    """
    app_value = _clean(app_value)
    if not app_value:
        return FieldResult(field=field, status="match", label_value=label_value,
                           application_value=None, note="Not specified in application; skipped.")
    if not label_value or not _clean(label_value):
        return FieldResult(field=field, status="missing", application_value=app_value,
                           note="Not found on the label.")
    label_value = _clean(label_value)

    if label_value == app_value:
        return FieldResult(field=field, status="match", label_value=label_value,
                           application_value=app_value)
    if label_value.lower() == app_value.lower():
        return FieldResult(field=field, status="match", label_value=label_value,
                           application_value=app_value,
                           note="Same text, different capitalization.")
    if _loose(label_value) == _loose(app_value):
        return FieldResult(field=field, status="match", label_value=label_value,
                           application_value=app_value,
                           note="Same text, minor punctuation/spacing difference.")
    ratio = _similarity(label_value, app_value)
    if ratio >= 0.85:
        return FieldResult(field=field, status="review", label_value=label_value,
                           application_value=app_value,
                           note="Very similar but not identical — needs human judgment "
                                "({:.0f}% similar).".format(ratio * 100))
    return FieldResult(field=field, status="mismatch", label_value=label_value,
                       application_value=app_value, note="Values do not match.")


# ----------------------------------------------------------------------- ABV

_PERCENT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
_PROOF_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*proof", re.IGNORECASE)
_BARE_NUM_RE = re.compile(r"^\s*(\d{1,3}(?:\.\d+)?)\s*$")
_ALC_NUM_RE = re.compile(r"alc[^0-9]*(\d{1,3}(?:\.\d+)?)", re.IGNORECASE)


def parse_abv(text: str) -> Tuple[Optional[float], Optional[float]]:
    """Return (abv_percent, proof) parsed from free text. Either may be None."""
    if not text:
        return None, None
    text = _clean(text)
    abv = None
    m = _PERCENT_RE.search(text)
    if m:
        abv = float(m.group(1))
    else:
        m = _BARE_NUM_RE.match(text) or _ALC_NUM_RE.search(text)
        if m:
            abv = float(m.group(1))
    proof = None
    m = _PROOF_RE.search(text)
    if m:
        proof = float(m.group(1))
    return abv, proof


def compare_abv(label_value: Optional[str], app_value: str) -> FieldResult:
    field = "alcohol_content"
    app_value = _clean(app_value)
    if not app_value:
        return FieldResult(field=field, status="match", label_value=label_value,
                           note="Not specified in application; skipped.")
    if not label_value:
        return FieldResult(field=field, status="missing", application_value=app_value,
                           note="Alcohol content not found on the label.")
    label_abv, label_proof = parse_abv(label_value)
    app_abv, app_proof = parse_abv(app_value)
    if label_abv is None and label_proof is not None:
        label_abv = label_proof / 2.0
    if app_abv is None and app_proof is not None:
        app_abv = app_proof / 2.0
    if label_abv is None or app_abv is None:
        return FieldResult(field=field, status="review", label_value=label_value,
                           application_value=app_value,
                           note="Could not parse a numeric ABV — verify manually.")
    if abs(label_abv - app_abv) > 0.05:
        return FieldResult(field=field, status="mismatch", label_value=label_value,
                           application_value=app_value,
                           note="Label says {:g}% but application says {:g}%.".format(label_abv, app_abv))
    # ABV agrees; sanity-check the proof statement if present (proof = 2 x ABV).
    if label_proof is not None and abs(label_proof - label_abv * 2) > 0.1:
        return FieldResult(field=field, status="review", label_value=label_value,
                           application_value=app_value,
                           note="ABV matches, but the proof on the label ({:g}) is not 2x the "
                                "ABV ({:g}%).".format(label_proof, label_abv))
    return FieldResult(field=field, status="match", label_value=label_value,
                       application_value=app_value)


# -------------------------------------------------------------- net contents

_VOLUME_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(ml|mls|milliliters?|millilitres?|cl|l|liters?|litres?|"
    r"fl\.?\s*oz\.?|fluid\s+ounces?|oz\.?|gal|gallons?)",
    re.IGNORECASE,
)
_UNIT_TO_ML = {
    "ml": 1.0, "cl": 10.0, "l": 1000.0, "floz": 29.5735, "oz": 29.5735,
    "gal": 3785.41,
}


def parse_volume_ml(text: str) -> Optional[float]:
    if not text:
        return None
    m = _VOLUME_RE.search(_clean(text))
    if not m:
        return None
    qty = float(m.group(1))
    unit = re.sub(r"[^a-z]", "", m.group(2).lower())
    if unit.startswith("ml") or unit.startswith("milli"):
        factor = _UNIT_TO_ML["ml"]
    elif unit.startswith("cl"):
        factor = _UNIT_TO_ML["cl"]
    elif unit.startswith("l"):
        factor = _UNIT_TO_ML["l"]
    elif unit.startswith("floz") or unit.startswith("fluid"):
        factor = _UNIT_TO_ML["floz"]
    elif unit.startswith("oz"):
        factor = _UNIT_TO_ML["oz"]
    elif unit.startswith("gal"):
        factor = _UNIT_TO_ML["gal"]
    else:
        return None
    return qty * factor


def compare_net_contents(label_value: Optional[str], app_value: str) -> FieldResult:
    field = "net_contents"
    app_value = _clean(app_value)
    if not app_value:
        return FieldResult(field=field, status="match", label_value=label_value,
                           note="Not specified in application; skipped.")
    if not label_value:
        return FieldResult(field=field, status="missing", application_value=app_value,
                           note="Net contents not found on the label.")
    label_ml = parse_volume_ml(label_value)
    app_ml = parse_volume_ml(app_value)
    if label_ml is None or app_ml is None:
        if _loose(label_value) == _loose(app_value):
            return FieldResult(field=field, status="match", label_value=label_value,
                               application_value=app_value)
        return FieldResult(field=field, status="review", label_value=label_value,
                           application_value=app_value,
                           note="Could not parse a volume — verify manually.")
    if abs(label_ml - app_ml) <= 0.5:
        note = None
        if _loose(label_value) != _loose(app_value):
            note = "Equivalent volume expressed in different units."
        return FieldResult(field=field, status="match", label_value=label_value,
                           application_value=app_value, note=note)
    return FieldResult(field=field, status="mismatch", label_value=label_value,
                       application_value=app_value,
                       note="Label is {:g} mL but application says {:g} mL.".format(label_ml, app_ml))


# -------------------------------------------------------- government warning

def _warning_diffs(label_text: str) -> List[str]:
    """Word-level differences between the label warning and the statutory text."""
    expected = _clean(GOVERNMENT_WARNING_TEXT).lower().split()
    actual = _clean(label_text).lower().split()
    diffs: List[str] = []
    matcher = difflib.SequenceMatcher(None, expected, actual)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        want = " ".join(expected[i1:i2]) or "(nothing)"
        got = " ".join(actual[j1:j2]) or "(nothing)"
        if op == "delete":
            diffs.append('missing: "{}"'.format(want))
        elif op == "insert":
            diffs.append('added: "{}"'.format(got))
        else:
            diffs.append('"{}" should be "{}"'.format(got, want))
    return diffs


def check_government_warning(extracted: ExtractedLabel) -> List[FieldResult]:
    """The warning must be word-for-word, with 'GOVERNMENT WARNING:' in caps and bold."""
    results: List[FieldResult] = []
    text = extracted.government_warning
    if not text or not _clean(text):
        results.append(FieldResult(
            field="government_warning", status="missing",
            note="Mandatory health warning statement (27 CFR Part 16) not found on the label."))
        return results

    # 1. Word-for-word text check (case handled separately below).
    diffs = _warning_diffs(text)
    if diffs:
        shown = "; ".join(diffs[:5])
        if len(diffs) > 5:
            shown += "; ... ({} more)".format(len(diffs) - 5)
        results.append(FieldResult(
            field="government_warning", status="mismatch", label_value=_clean(text),
            application_value=GOVERNMENT_WARNING_TEXT,
            note="Warning text deviates from the required statement: " + shown))
    else:
        results.append(FieldResult(
            field="government_warning", status="match", label_value=_clean(text),
            application_value=GOVERNMENT_WARNING_TEXT,
            note="Word-for-word match with the required statement."))

    # 2. "GOVERNMENT WARNING:" must be in capital letters.
    prefix = extracted.warning_prefix_verbatim or _clean(text)[:20]
    if prefix.upper().startswith("GOVERNMENT WARNING") and not prefix.startswith("GOVERNMENT WARNING"):
        results.append(FieldResult(
            field="warning_capitalization", status="mismatch", label_value=prefix,
            application_value="GOVERNMENT WARNING:",
            note='"GOVERNMENT WARNING:" must appear in capital letters; label shows "{}".'.format(prefix)))
    elif prefix.startswith("GOVERNMENT WARNING"):
        results.append(FieldResult(
            field="warning_capitalization", status="match", label_value=prefix,
            application_value="GOVERNMENT WARNING:"))
    else:
        results.append(FieldResult(
            field="warning_capitalization", status="review", label_value=prefix,
            application_value="GOVERNMENT WARNING:",
            note="Could not confirm the warning lead-in — verify capitalization manually."))

    # 3. Bold type — vision models can't certify typography, so never auto-pass.
    bold = (extracted.warning_appears_bold or "unclear").lower()
    if bold == "no":
        results.append(FieldResult(
            field="warning_bold", status="mismatch",
            note='"GOVERNMENT WARNING:" does not appear to be in bold type.'))
    elif bold == "yes":
        results.append(FieldResult(
            field="warning_bold", status="match",
            note='"GOVERNMENT WARNING:" appears to be in bold type (visual estimate — '
                 "confirm on final artwork)."))
    else:
        results.append(FieldResult(
            field="warning_bold", status="review",
            note="Could not determine whether the warning lead-in is bold — verify manually."))
    return results


# --------------------------------------------------------------------- driver

def verify(application: ApplicationData, extracted: ExtractedLabel) -> VerificationResult:
    fields: List[FieldResult] = [
        compare_text_field("brand_name", extracted.brand_name, application.brand_name),
        compare_text_field("class_type", extracted.class_type, application.class_type),
        compare_abv(extracted.alcohol_content, application.alcohol_content),
        compare_net_contents(extracted.net_contents, application.net_contents),
    ]
    fields.extend(check_government_warning(extracted))

    statuses = {f.status for f in fields}
    if "mismatch" in statuses or "missing" in statuses:
        overall = "fail"
    elif "review" in statuses:
        overall = "review"
    else:
        overall = "pass"
    if extracted.image_legibility == "poor" and overall == "pass":
        overall = "review"
    return VerificationResult(
        overall=overall, fields=fields,
        image_legibility=extracted.image_legibility,
        legibility_notes=extracted.legibility_notes,
    )
