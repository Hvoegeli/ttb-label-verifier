"""Tests for the shared country-of-origin rule (app/rules/origin.py).

The rule is conditional and deliberately never hard-FAILs on a photo inference:
it PASSes when an origin is stated or nothing suggests an import, and routes to
NEEDS REVIEW when the label looks imported but no origin was read. These tests
pin every branch, the per-beverage citation, and the end-to-end verdict through
the dispatcher for all three beverages.
"""
import pytest

from app.models import ExtractedFields
from app.rules import origin, overall_verdict, run_rules
from app.rules.base import FAIL, PASS, REVIEW
from app.rules.warning import CANONICAL


def _spirits(**over):
    base = dict(
        brand_name="OLD TOM DISTILLERY", class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)", net_contents="750 mL",
        name_and_address="Bottled by Old Tom Distillery, Bardstown, KY",
        government_warning=CANONICAL, warning_legible=True, overall_legible=True,
    )
    base.update(over)
    return ExtractedFields(**base)


# ---- the rule in isolation ------------------------------------------------

def test_stated_origin_passes():
    out = origin.check(_spirits(country_of_origin="Product of Scotland", appears_imported=True), "spirits")
    assert out.status == PASS
    assert "Scotland" in out.reason


def test_domestic_no_indicators_passes():
    # appears_imported False and no origin statement: not required, so PASS.
    out = origin.check(_spirits(appears_imported=False), "spirits")
    assert out.status == PASS


def test_unknown_import_status_passes():
    # appears_imported None (model unsure) and no origin: conservative PASS, not REVIEW.
    out = origin.check(_spirits(appears_imported=None), "spirits")
    assert out.status == PASS


def test_imported_without_origin_reviews():
    out = origin.check(_spirits(appears_imported=True, country_of_origin=None), "spirits")
    assert out.status == REVIEW
    assert "imported" in out.reason.lower()


def test_imported_without_origin_never_fails():
    # The whole point: an uncertain import inference must not auto-FAIL.
    out = origin.check(_spirits(appears_imported=True, country_of_origin=None), "spirits")
    assert out.status != FAIL


def test_illegible_image_reviews_with_a_different_reason():
    clear = origin.check(_spirits(appears_imported=True, overall_legible=True), "spirits")
    blurry = origin.check(_spirits(appears_imported=True, overall_legible=False), "spirits")
    assert clear.status == REVIEW and blurry.status == REVIEW
    assert "not clearly readable" in blurry.reason
    assert "not clearly readable" not in clear.reason


def test_stated_origin_wins_even_if_not_flagged_imported():
    # A printed origin satisfies the rule regardless of the appears_imported flag.
    out = origin.check(_spirits(country_of_origin="Product of France", appears_imported=None), "spirits")
    assert out.status == PASS


@pytest.mark.parametrize("beverage,expected", [
    ("spirits", "27 CFR 5.69"),
    ("beer", "27 CFR 7.69"),
    ("wine", "19 CFR 134"),
    ("unknown", "27 CFR 5.69"),  # safe default
])
def test_citation_per_beverage(beverage, expected):
    out = origin.check(_spirits(appears_imported=False), beverage)
    assert out.citation == expected


def test_rule_is_golden():
    # Golden so a triggered-missing case routes the whole label to NEEDS REVIEW.
    assert origin.check(_spirits(appears_imported=False), "spirits").golden is True


# ---- through the dispatcher (verdict effect) ------------------------------

def test_imported_no_origin_makes_otherwise_clean_label_review():
    fields = _spirits(appears_imported=True, country_of_origin=None)
    outcomes = run_rules(fields, "spirits")
    assert any(o.field == "Country of origin" for o in outcomes)
    assert overall_verdict(outcomes, fields.overall_legible) == REVIEW


def test_clean_domestic_label_still_passes():
    fields = _spirits(appears_imported=False)
    outcomes = run_rules(fields, "spirits")
    assert overall_verdict(outcomes, fields.overall_legible) == PASS


@pytest.mark.parametrize("beverage", ["spirits", "wine", "beer"])
def test_origin_check_present_in_every_ruleset(beverage):
    outcomes = run_rules(ExtractedFields(government_warning=CANONICAL), beverage)
    assert any(o.field == "Country of origin" for o in outcomes), f"{beverage} missing origin check"
