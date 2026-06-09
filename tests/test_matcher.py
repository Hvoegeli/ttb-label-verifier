"""Unit tests for the label-vs-application match check."""
import json
from pathlib import Path

from app.matcher import MATCH, MISMATCH, NA, compare
from app.models import ExtractedFields
from app.rules.warning import CANONICAL


def fields(**overrides):
    base = dict(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        name_and_address="Old Tom Distillery, Bardstown, KY",
        government_warning=CANONICAL,
    )
    base.update(overrides)
    return ExtractedFields(**base)


def _by_field(outcomes):
    return {o.field: o for o in outcomes}


def test_brand_matches_despite_case_and_punctuation():
    out = _by_field(compare(fields(brand_name="STONE'S THROW"), {"brand_name": "Stone's Throw"}))
    assert out["Brand name"].status == MATCH
    assert "normaliz" in out["Brand name"].note


def test_alcohol_matches_on_value_ignoring_proof():
    out = _by_field(compare(fields(), {"alcohol_content": "45% Alc/Vol"}))
    assert out["Alcohol content"].status == MATCH


def test_alcohol_value_mismatch_detected():
    out = _by_field(compare(fields(), {"alcohol_content": "40% Alc/Vol"}))
    assert out["Alcohol content"].status == MISMATCH


def test_net_contents_matches_on_volume():
    out = _by_field(compare(fields(), {"net_contents": "750ml"}))
    assert out["Net contents"].status == MATCH


def test_net_contents_volume_mismatch():
    out = _by_field(compare(fields(), {"net_contents": "700 mL"}))
    assert out["Net contents"].status == MISMATCH


def test_warning_compared_exactly():
    assert _by_field(compare(fields(), {"government_warning": CANONICAL}))["Government warning"].status == MATCH
    altered = CANONICAL.replace("health problems.", "health issues.")
    assert _by_field(compare(fields(), {"government_warning": altered}))["Government warning"].status == MISMATCH


def test_only_provided_fields_are_compared():
    outcomes = compare(fields(), {"brand_name": "Old Tom Distillery"})
    assert len(outcomes) == 1
    assert outcomes[0].field == "Brand name"


def test_missing_label_value_is_not_applicable():
    out = _by_field(compare(fields(class_type=None), {"class_type": "Vodka"}))
    assert out["Class/type designation"].status == NA


def test_fanciful_name_present_on_label_matches():
    out = _by_field(compare(fields(brand_name="OLD TOM DISTILLERY RESERVE"), {"fanciful_name": "Reserve"}))
    assert out["Fanciful name"].status == MATCH


def test_fanciful_name_absent_from_label_mismatches():
    out = _by_field(compare(fields(), {"fanciful_name": "Midnight"}))
    assert out["Fanciful name"].status == MISMATCH


def test_wine_fields_match_on_application():
    wf = fields(class_type="Cabernet Sauvignon", appellation="Napa Valley",
                grape_varietal="Cabernet Sauvignon", vintage="2019")
    out = _by_field(compare(wf, {"appellation": "napa valley", "vintage": "2019"}))
    assert out["Appellation"].status == MATCH
    assert out["Vintage"].status == MATCH


def test_example_mismatch_file_flags_alcohol():
    app_data = json.loads((Path(__file__).parent.parent / "examples" / "application_mismatch.json").read_text())
    out = _by_field(compare(fields(), app_data))
    assert out["Alcohol content"].status == MISMATCH
    assert out["Brand name"].status == MATCH
    assert out["Net contents"].status == MATCH
