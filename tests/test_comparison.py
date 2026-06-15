"""Unit tests for the deterministic verification engine."""
import pytest

from app.comparison import (GOVERNMENT_WARNING_TEXT, check_government_warning,
                            compare_abv, compare_net_contents,
                            compare_text_field, parse_abv, parse_volume_ml,
                            verify)
from app.schemas import ApplicationData, ExtractedLabel


def make_extracted(**overrides):
    base = dict(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        government_warning=GOVERNMENT_WARNING_TEXT,
        warning_prefix_verbatim="GOVERNMENT WARNING:",
        warning_appears_bold="yes",
        image_legibility="good",
    )
    base.update(overrides)
    return ExtractedLabel(**base)


APP = ApplicationData(
    brand_name="OLD TOM DISTILLERY",
    class_type="Kentucky Straight Bourbon Whiskey",
    alcohol_content="45% Alc./Vol. (90 Proof)",
    net_contents="750 mL",
)


# ----------------------------------------------------------- text fields

def test_brand_exact_match():
    assert compare_text_field("brand_name", "OLD TOM", "OLD TOM").status == "match"


def test_brand_case_difference_is_match_with_note():
    # Dave's example: STONE'S THROW vs Stone's Throw
    r = compare_text_field("brand_name", "STONE'S THROW", "Stone's Throw")
    assert r.status == "match"
    assert "capitalization" in r.note.lower()


def test_brand_smart_quote_difference_is_match():
    r = compare_text_field("brand_name", "STONE’S THROW", "STONE'S THROW")
    assert r.status == "match"


def test_brand_close_but_different_needs_review():
    r = compare_text_field("brand_name", "OLD TOM DISTILLERS", "OLD TOM DISTILLERY")
    assert r.status == "review"


def test_brand_totally_different_is_mismatch():
    assert compare_text_field("brand_name", "RIVERBEND", "OLD TOM").status == "mismatch"


def test_brand_absent_from_label_is_missing():
    assert compare_text_field("brand_name", None, "OLD TOM").status == "missing"


def test_empty_application_field_is_skipped():
    assert compare_text_field("class_type", "Vodka", "").status == "match"


# ------------------------------------------------------------------- ABV

@pytest.mark.parametrize("text,abv,proof", [
    ("45% Alc./Vol. (90 Proof)", 45.0, 90.0),
    ("ALC. 47% BY VOL.", 47.0, None),
    ("40", 40.0, None),
    ("80 proof", None, 80.0),
    ("13.5% ABV", 13.5, None),
])
def test_parse_abv(text, abv, proof):
    assert parse_abv(text) == (abv, proof)


def test_abv_match_across_formats():
    assert compare_abv("45% ALC/VOL", "45").status == "match"


def test_abv_mismatch():
    r = compare_abv("43% Alc./Vol.", "45% Alc./Vol.")
    assert r.status == "mismatch"


def test_abv_proof_inconsistent_with_abv_flags_review():
    r = compare_abv("45% Alc./Vol. (86 Proof)", "45%")
    assert r.status == "review"


def test_abv_unparseable_is_review_not_silent_pass():
    assert compare_abv("forty-five percent", "45%").status == "review"


# ----------------------------------------------------------- net contents

@pytest.mark.parametrize("text,ml", [
    ("750 mL", 750.0),
    ("1 L", 1000.0),
    ("75 cl", 750.0),
    ("25.4 FL OZ", pytest.approx(751.17, abs=0.1)),
])
def test_parse_volume(text, ml):
    assert parse_volume_ml(text) == ml


def test_net_contents_unit_conversion_match():
    r = compare_net_contents("1 L", "1000 mL")
    assert r.status == "match"
    assert "different units" in r.note


def test_net_contents_mismatch():
    assert compare_net_contents("700 mL", "750 mL").status == "mismatch"


# ----------------------------------------------------- government warning

def _by_field(results):
    return {r.field: r for r in results}


def test_perfect_warning_passes_all_three_checks():
    results = _by_field(check_government_warning(make_extracted()))
    assert results["government_warning"].status == "match"
    assert results["warning_capitalization"].status == "match"
    assert results["warning_bold"].status == "match"


def test_missing_warning_is_missing():
    results = check_government_warning(make_extracted(government_warning=None))
    assert results[0].status == "missing"


def test_title_case_prefix_caught():
    # Jenny's real-world catch: "Government Warning" in title case -> reject.
    e = make_extracted(
        government_warning="Government Warning: " + GOVERNMENT_WARNING_TEXT.split(": ", 1)[1],
        warning_prefix_verbatim="Government Warning:")
    results = _by_field(check_government_warning(e))
    assert results["warning_capitalization"].status == "mismatch"
    # Body text is still word-for-word, so the text check itself passes.
    assert results["government_warning"].status == "match"


def test_reworded_warning_caught_with_diff():
    e = make_extracted(government_warning=GOVERNMENT_WARNING_TEXT.replace("drink", "consume"))
    r = _by_field(check_government_warning(e))["government_warning"]
    assert r.status == "mismatch"
    assert "consume" in r.note and "drink" in r.note


def test_truncated_warning_caught():
    e = make_extracted(
        government_warning=GOVERNMENT_WARNING_TEXT.replace(", and may cause health problems", ""))
    r = _by_field(check_government_warning(e))["government_warning"]
    assert r.status == "mismatch"
    assert "health problems" in r.note


def test_unclear_bold_is_review_never_autopass():
    e = make_extracted(warning_appears_bold="unclear")
    assert _by_field(check_government_warning(e))["warning_bold"].status == "review"


# ----------------------------------------------------------------- driver

def test_overall_pass():
    assert verify(APP, make_extracted()).overall == "pass"


def test_overall_fail_on_any_mismatch():
    assert verify(APP, make_extracted(alcohol_content="43%")).overall == "fail"


def test_overall_review_when_only_soft_flags():
    assert verify(APP, make_extracted(warning_appears_bold="unclear")).overall == "review"


def test_poor_legibility_downgrades_pass_to_review():
    assert verify(APP, make_extracted(image_legibility="poor")).overall == "review"
