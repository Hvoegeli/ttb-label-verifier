"""Mandatory label elements present (27 CFR 5.63).

Distilled spirits must carry: brand name, class/type, alcohol content, net
contents, name and address, and the health warning. Two nuances from the
regulations are honored here:

  - Brand name fallback (27 CFR 5.64(a)): if there is no separate brand name, the
    bottler/importer name in the name-and-address statement serves as the brand.
    So a missing brand alone does not fail when name and address is present.
  - If the image was not clearly legible, a missing field is more likely a read
    failure than a real omission, so the outcome is NEEDS REVIEW, not FAIL.
"""
from .base import FAIL, PASS, REVIEW, RuleOutcome

FIELD = "Mandatory fields"
CITATION = "27 CFR 5.63"


def _missing(value: str | None) -> bool:
    return not value or not value.strip()


def check(fields) -> RuleOutcome:
    missing = []
    if _missing(fields.class_type):
        missing.append("class/type")
    if _missing(fields.alcohol_content):
        missing.append("alcohol content")
    if _missing(fields.net_contents):
        missing.append("net contents")
    if _missing(fields.name_and_address):
        missing.append("name and address")
    if _missing(fields.government_warning):
        missing.append("government warning")
    # Brand satisfied if a brand name OR a name-and-address statement is present.
    if _missing(fields.brand_name) and _missing(fields.name_and_address):
        missing.append("brand name")

    if not missing:
        return RuleOutcome(FIELD, PASS, "All mandatory elements are present.", CITATION)

    listed = ", ".join(missing)
    if not fields.overall_legible:
        return RuleOutcome(FIELD, REVIEW, f"Could not find: {listed}. The image was not clearly readable, so review by hand.", CITATION)
    return RuleOutcome(FIELD, FAIL, f"Missing mandatory element(s): {listed}.", CITATION, {"missing": missing})
