"""Unit tests for the malt beverage rule set (27 CFR Part 7)."""
from app.models import ExtractedFields
from app.rules import FAIL, PASS, REVIEW, beer
from app.rules.warning import CANONICAL


def bfields(**overrides):
    base = dict(
        brand_name="RIVERBED BREWING",
        class_type="India Pale Ale",
        alcohol_content="6.5% Alc/Vol",
        net_contents="12 FL OZ",
        name_and_address="Brewed by Riverbed Brewing Co., Portland, OR",
        government_warning=CANONICAL,
        is_flavored_malt_beverage=False,
    )
    base.update(overrides)
    return ExtractedFields(**base)


def test_beer_has_no_standard_of_fill_check():
    # Beer has no federal standards of fill, so the rule set emits no fill row.
    emitted = {o.field for o in beer.run(bfields(net_contents="40 FL OZ"))}
    assert "Net contents" not in emitted


def test_beer_abv_optional_for_ordinary_beer():
    assert beer.check_abv(bfields(alcohol_content=None)).status == PASS


def test_beer_fmb_requires_abv():
    assert beer.check_abv(bfields(alcohol_content=None, is_flavored_malt_beverage=True)).status == FAIL


def test_beer_abv_abbreviation_flagged():
    # "ABV" is not an authorized abbreviation (27 CFR 7.65(b)(4)).
    assert beer.check_abv(bfields(alcohol_content="5% ABV")).status == REVIEW
    # but the proper "alc/vol" form passes
    assert beer.check_abv(bfields(alcohol_content="5% alc/vol")).status == PASS


def test_beer_classtype_recognized():
    for ct in ("India Pale Ale", "Lager", "Stout", "Malt Liquor", "Hefeweizen", "Porter"):
        assert beer.check_classtype(bfields(class_type=ct)).status == PASS, ct


def test_beer_unrecognized_classtype_reviews():
    assert beer.check_classtype(bfields(class_type="Fizzy Drink", statement_of_composition=None)).status == REVIEW
