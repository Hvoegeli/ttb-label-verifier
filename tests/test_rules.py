"""Unit tests for the deterministic rule engine.

These take field values directly (no image, no model), so they are fast,
deterministic, and prove rule correctness in isolation. Each case maps to a
specific regulation from the project's TTB diff.
"""
from app.models import ExtractedFields
from app.rules import FAIL, PASS, REVIEW, overall_verdict, run_rules
from app.rules import abv, classtype, fill, presence, warning


def fields(**overrides):
    base = dict(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        name_and_address="Bottled by Old Tom Distillery, Bardstown, KY",
        government_warning=warning.CANONICAL,
        warning_legible=True,
        overall_legible=True,
    )
    base.update(overrides)
    return ExtractedFields(**base)


# --- Government warning (27 CFR 16.21 / 16.22) ---

def test_warning_exact_passes():
    assert warning.check(fields()).status == PASS


def test_warning_tolerates_extra_whitespace():
    spaced = "  " + warning.CANONICAL.replace(" ", "  ")
    assert warning.check(fields(government_warning=spaced)).status == PASS


def test_warning_all_caps_passes():
    # Real bottles print the whole warning in capitals; only "GOVERNMENT WARNING"
    # is required to be capitalized, so an all-caps body is compliant.
    assert warning.check(fields(government_warning=warning.CANONICAL.upper())).status == PASS


def test_warning_title_case_fails_on_capitals():
    titled = warning.CANONICAL.replace("GOVERNMENT WARNING", "Government Warning")
    out = warning.check(fields(government_warning=titled))
    assert out.status == FAIL
    assert "capital letters" in out.reason


def test_warning_missing_second_sentence_fails():
    cut = warning.CANONICAL.split(" (2)")[0]  # drop sentence 2
    out = warning.check(fields(government_warning=cut))
    assert out.status == FAIL
    assert "second" in out.reason.lower()


def test_warning_altered_wording_fails():
    altered = warning.CANONICAL.replace("health problems.", "health issues.")
    assert warning.check(fields(government_warning=altered)).status == FAIL


def test_warning_garbled_but_flagged_routes_to_review():
    out = warning.check(fields(government_warning="GOVERNMENT W@RN1NG blurry...", warning_legible=False))
    assert out.status == REVIEW


def test_warning_missing_and_legible_fails():
    out = warning.check(fields(government_warning=None))
    assert out.status == FAIL


def test_warning_missing_and_illegible_reviews():
    out = warning.check(fields(government_warning=None, overall_legible=False))
    assert out.status == REVIEW


def test_warning_carries_tier2_advisory():
    out = warning.check(fields())
    assert out.detail and "tier2_advisory" in out.detail


# --- Standards of fill (27 CFR 5.203) ---

def test_fill_authorized_sizes_pass():
    for size in ("750 mL", "1.75 L", "750ml", "1.0 L", "720 mL", "50 mL"):
        assert fill.check(fields(net_contents=size)).status == PASS, size


def test_fill_offlist_sizes_fail():
    for size in ("800 mL", "725 mL", "1.6 L"):
        assert fill.check(fields(net_contents=size)).status == FAIL, size


def test_fill_unparseable_reviews():
    assert fill.check(fields(net_contents="one bottle")).status == REVIEW


# --- Alcohol content (27 CFR 5.65) ---

def test_abv_percent_by_volume_passes():
    assert abv.check(fields(alcohol_content="45% Alc./Vol.")).status == PASS


def test_abv_proof_alongside_percent_passes():
    assert abv.check(fields(alcohol_content="45% Alc./Vol. (90 Proof)")).status == PASS


def test_abv_proof_alone_fails():
    out = abv.check(fields(alcohol_content="90 Proof"))
    assert out.status == FAIL
    assert "proof alone" in out.reason.lower()


def test_abv_bare_percent_without_alcvol_reviews():
    assert abv.check(fields(alcohol_content="45%")).status == REVIEW


# --- Class/type (27 CFR 5.141-5.143) ---

def test_classtype_recognized_passes():
    for ct in ("Kentucky Straight Bourbon Whiskey", "Vodka", "London Dry Gin", "Single Malt Scotch Whisky"):
        assert classtype.check(fields(class_type=ct)).status == PASS, ct


def test_classtype_unrecognized_reviews():
    assert classtype.check(fields(class_type="Mystery Elixir")).status == REVIEW


def test_classtype_age_and_cream_recognized():
    # Designations the real-photo eval flagged as benign reviews now pass.
    for ct in ("Añejo", "AÑEJO", "Anejo", "Reposado", "Blanco", "Irish Cream", "Cream Liqueur"):
        assert classtype.check(fields(class_type=ct)).status == PASS, ct


# --- Mandatory presence (27 CFR 5.63) ---

def test_presence_all_present_passes():
    assert presence.check(fields()).status == PASS


def test_presence_missing_net_contents_fails():
    out = presence.check(fields(net_contents=None))
    assert out.status == FAIL
    assert "net contents" in out.reason


def test_presence_brand_fallback_to_name_and_address():
    # No brand name, but a name-and-address statement is present -> not a failure (5.64(a)).
    assert presence.check(fields(brand_name=None)).status == PASS


def test_presence_brand_and_name_both_missing_fails():
    out = presence.check(fields(brand_name=None, name_and_address=None))
    assert out.status == FAIL
    assert "brand name" in out.reason


def test_presence_missing_when_illegible_reviews():
    out = presence.check(fields(class_type=None, overall_legible=False))
    assert out.status == REVIEW


# --- Engine aggregation (FAIL > REVIEW > PASS) ---

def test_run_rules_all_compliant_overall_pass():
    outcomes = run_rules(fields())
    assert len(outcomes) == 5
    assert all(o.citation for o in outcomes)
    assert overall_verdict(outcomes, True) == PASS


def test_one_violation_makes_overall_fail():
    outcomes = run_rules(fields(net_contents="800 mL"))
    assert overall_verdict(outcomes, True) == FAIL


def test_only_review_makes_overall_review():
    outcomes = run_rules(fields(class_type="Mystery Elixir"))
    assert FAIL not in {o.status for o in outcomes}
    assert overall_verdict(outcomes, True) == REVIEW


def test_fail_beats_review():
    # A FAIL anywhere wins over a REVIEW elsewhere.
    outcomes = run_rules(fields(net_contents="800 mL", class_type="Mystery Elixir"))
    assert overall_verdict(outcomes, True) == FAIL


def test_illegible_forces_review_even_with_no_outcomes():
    assert overall_verdict([], overall_legible=False) == REVIEW


# --- Readability of reasons and citations ---

def test_fill_failure_is_plain_and_suggests_nearest_sizes():
    out = fill.check(fields(net_contents="800 mL"))
    assert out.status == FAIL
    assert "(800 mL)" not in out.reason  # no duplicated value
    assert "nearest authorized sizes" in out.reason.lower()
    assert "750 mL" in out.reason and "900 mL" in out.reason


def test_rule_row_carries_plain_citation_gloss():
    row = fill.check(fields(net_contents="800 mL")).as_row()
    assert row["citation"] == "27 CFR 5.203"
    assert row["citation_plain"] == "Authorized bottle size"
