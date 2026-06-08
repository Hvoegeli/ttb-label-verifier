"""Malt beverage / beer rule set (27 CFR Part 7).

Part 7 was renumbered by the 2022 modernization, so citations use the current
section numbers. The distinctive beer rules versus spirits and wine:

  - There are NO federal standards of fill for malt beverages, so there is no
    authorized-size check (any container size is allowed). A net-contents
    statement is still mandatory; only its presence is checked.
  - Alcohol content is usually OPTIONAL federally (27 CFR 7.65(a)); it is
    mandatory only for flavored malt beverages (27 CFR 7.63(a)(3)). A missing ABV
    on an ordinary beer is therefore not a failure.
  - "ABV" is not an authorized abbreviation (27 CFR 7.65(b)(4) allows only alc,
    vol, %, and /); using it routes to review.
  - There is no proof statement for beer.

The Government Warning (27 CFR Part 16) is shared with every beverage.
"""
import re

from . import warning
from .base import FAIL, PASS, REVIEW, RuleOutcome

# Recognized malt beverage class/type designations (lowercased), modifier-tolerant.
RECOGNIZED = {
    "malt beverage", "beer", "ale", "lager", "porter", "stout", "malt liquor",
    "pilsner", "pilsener", "ipa", "india pale ale", "pale ale", "bock", "doppelbock",
    "hefeweizen", "weiss", "weisse", "wheat beer", "witbier", "saison", "kolsch",
    "kölsch", "dunkel", "marzen", "märzen", "oktoberfest", "amber ale", "brown ale",
    "cream ale", "golden ale", "blonde ale", "barleywine", "barley wine", "gose",
    "lambic", "tripel", "dubbel", "pale lager", "dark lager", "imperial stout",
}

_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent)")
_ALCVOL = re.compile(r"alc|vol")
_ABV = re.compile(r"\babv\b")
STATE_LAW_ADVISORY = {"tier2_advisory": "Alcohol content is optional for ordinary malt beverages federally (27 CFR 7.65(a)) but some States require or prohibit it. Confirm against the destination State's law."}


def _missing(value) -> bool:
    return not value or (isinstance(value, str) and not value.strip())


def check_presence(fields) -> RuleOutcome:
    """Mandatory elements for malt beverages (27 CFR 7.63). Net contents is
    required, but there is no standard-of-fill check. Alcohol content is handled
    in its own rule because it is conditional."""
    missing = []
    if _missing(fields.class_type):
        missing.append("class/type")
    if _missing(fields.net_contents):
        missing.append("net contents")
    if _missing(fields.name_and_address):
        missing.append("name and address")
    if _missing(fields.government_warning):
        missing.append("government warning")
    if _missing(fields.brand_name) and _missing(fields.name_and_address):
        missing.append("brand name")

    if not missing:
        return RuleOutcome("Mandatory fields", PASS, "All mandatory elements are present.", "27 CFR 7.63")
    listed = ", ".join(missing)
    if not fields.overall_legible:
        return RuleOutcome("Mandatory fields", REVIEW, f"Could not find: {listed}. The image was not clearly readable, so review by hand.", "27 CFR 7.63")
    return RuleOutcome("Mandatory fields", FAIL, f"Missing mandatory element(s): {listed}.", "27 CFR 7.63", {"missing": missing})


def check_classtype(fields) -> RuleOutcome:
    """Recognized malt beverage designation (27 CFR 7.142), or a statement of
    composition (27 CFR 7.147) which routes to human review."""
    raw = fields.class_type
    if _missing(raw):
        if not _missing(fields.statement_of_composition):
            return RuleOutcome("Class/type", REVIEW, "No standard class shown; a statement of composition is used and a human should confirm it.", "27 CFR 7.147")
        return RuleOutcome("Class/type", REVIEW, "Class/type not found; see the mandatory-fields check.", "27 CFR 7.142")
    low = raw.lower()
    if any(term in low for term in RECOGNIZED):
        return RuleOutcome("Class/type", PASS, f"'{raw}' is a recognized malt beverage designation.", "27 CFR 7.142")
    return RuleOutcome("Class/type", REVIEW, f"'{raw}' is not a recognized class. It may be a statement of composition; a human should confirm.", "27 CFR 7.147")


def check_abv(fields) -> RuleOutcome:
    """Alcohol content for malt beverages (27 CFR 7.65).

    Mandatory only for flavored malt beverages; otherwise optional. "ABV" is not
    an authorized abbreviation.
    """
    raw = fields.alcohol_content
    is_fmb = fields.is_flavored_malt_beverage is True

    if _missing(raw):
        if is_fmb:
            return RuleOutcome("Alcohol content", FAIL, "This is a flavored malt beverage, which must state alcohol content, but none was found.", "27 CFR 7.63(a)(3)")
        return RuleOutcome("Alcohol content", PASS, "No alcohol statement, which is allowed for an ordinary malt beverage (optional federally).", "27 CFR 7.65", STATE_LAW_ADVISORY)

    low = raw.lower()
    has_percent = bool(_PERCENT.search(low))
    has_alcvol = bool(_ALCVOL.search(low))
    uses_abv = bool(_ABV.search(low))

    if uses_abv and not has_alcvol:
        return RuleOutcome("Alcohol content", REVIEW, "Uses the abbreviation 'ABV', which is not authorized; only 'alc', 'vol', '%' and '/' may abbreviate the statement. Confirm wording.", "27 CFR 7.65(b)(4)")
    if has_percent and has_alcvol:
        return RuleOutcome("Alcohol content", PASS, "States percent alcohol by volume in an accepted form.", "27 CFR 7.65")
    if has_percent:
        return RuleOutcome("Alcohol content", REVIEW, f"A percentage is shown but not clearly labeled as alcohol by volume in '{raw}'. Verify by hand.", "27 CFR 7.65")
    return RuleOutcome("Alcohol content", REVIEW, f"Could not confirm an alcohol by volume statement in '{raw}'. Verify by hand.", "27 CFR 7.65")


def run(fields) -> list[RuleOutcome]:
    """Apply all malt beverage rules in label-reading order (no fill check)."""
    return [
        check_presence(fields),
        check_classtype(fields),
        check_abv(fields),
        warning.check(fields),
    ]
