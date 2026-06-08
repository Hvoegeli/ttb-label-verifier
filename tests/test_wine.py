"""Unit tests for the wine rule set (27 CFR Part 4)."""
from app.models import ExtractedFields
from app.rules import FAIL, PASS, REVIEW, wine
from app.rules.warning import CANONICAL


def wfields(**overrides):
    base = dict(
        brand_name="STONECREST CELLARS",
        class_type="Cabernet Sauvignon",
        alcohol_content="13.5% Alc./Vol.",
        net_contents="750 mL",
        name_and_address="Bottled by Stonecrest Cellars, Napa, CA",
        government_warning=CANONICAL,
        appellation="Napa Valley",
        vintage="2019",
        grape_varietal="Cabernet Sauvignon",
        sulfite_statement="Contains Sulfites",
    )
    base.update(overrides)
    return ExtractedFields(**base)


def test_wine_fill_uses_the_wine_list_not_spirits():
    # 2.25 L is a wine size (2025); 900 mL is a spirits size but NOT a wine size.
    assert wine.check_fill(wfields(net_contents="2.25 L")).status == PASS
    assert wine.check_fill(wfields(net_contents="900 mL")).status == FAIL


def test_wine_large_format_exempt():
    assert wine.check_fill(wfields(net_contents="18 L")).status == PASS


def test_wine_table_wine_may_omit_numeric_abv():
    assert wine.check_abv(wfields(class_type="Red Table Wine", alcohol_content=None)).status == PASS


def test_wine_non_table_requires_abv():
    assert wine.check_abv(wfields(alcohol_content=None)).status == FAIL


def test_wine_appellation_is_conditional():
    assert wine.check_appellation(wfields()).status == PASS                      # present when required
    assert wine.check_appellation(wfields(appellation=None)).status == REVIEW    # required, missing
    assert wine.check_appellation(
        wfields(grape_varietal=None, vintage=None, appellation=None)
    ).status == PASS                                                             # not triggered


def test_wine_sulfite_is_advisory_and_non_gating():
    out = wine.check_sulfite(wfields(sulfite_statement=None))
    assert out.golden is False
    assert out.status == REVIEW
