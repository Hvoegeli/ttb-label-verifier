"""Country of origin for imported products (shared across all beverages).

This is the one mandatory label element from the take-home brief that is NOT a
pure TTB rule. TTB's own sections defer to U.S. Customs and Border Protection
marking rules (19 CFR parts 102 and 134):

  - Distilled spirits: 27 CFR 5.69
  - Malt beverages:    27 CFR 7.69
  - Wine (Part 4 was not modernized, so no parallel section): the CBP rule applies
    directly (19 CFR part 134).

Design (mirrors the wine appellation check): country of origin is *conditional*,
required only when the product is an import, and whether a single photo even shows
an import is genuinely hard to prove. So this rule NEVER hard-FAILs on a photo
inference. It can only:

  - PASS when a country-of-origin statement is present, or when nothing on the
    label suggests an import (a domestic product does not need one); or
  - NEEDS REVIEW when the label looks imported but no origin statement was read,
    flagging a human rather than auto-failing on an uncertain read.

Known limitation, documented on purpose: a false "not imported" read (the model
misses subtle import language) lets an import through as PASS. The conservative
choice is deliberate, because the alternative (auto-FAIL on a guessed import) would
wrongly reject compliant domestic labels. A human still spot-checks cleared labels.
"""
from .base import PASS, REVIEW, RuleOutcome

FIELD = "Country of origin"

# Per-beverage controlling citation. Spirits and malt beverages have a TTB section
# that points to the CBP marking rule; wine relies on the CBP rule directly.
_CITATION = {
    "spirits": "27 CFR 5.69",
    "beer": "27 CFR 7.69",
    "wine": "19 CFR 134",
}


def _missing(value) -> bool:
    return not value or (isinstance(value, str) and not value.strip())


def check(fields, beverage: str = "spirits") -> RuleOutcome:
    citation = _CITATION.get(beverage, "27 CFR 5.69")
    co = fields.country_of_origin

    if not _missing(co):
        return RuleOutcome(FIELD, PASS, f"Country of origin '{co}' is stated.", citation)

    if fields.appears_imported is True:
        if not fields.overall_legible:
            return RuleOutcome(
                FIELD, REVIEW,
                "The product appears imported but no country of origin was read, and "
                "the image was not clearly readable. Review by hand.",
                citation,
            )
        return RuleOutcome(
            FIELD, REVIEW,
            "The product appears to be imported, which must declare its country of "
            "origin (U.S. Customs marking, 19 CFR part 134), but none was read. "
            "Confirm against the physical bottle.",
            citation,
        )

    return RuleOutcome(
        FIELD, PASS,
        "No import indicators were read; a country of origin statement is required "
        "only for imported products.",
        citation,
    )
