"""Wine rule set (27 CFR Part 4).

Part 4 was NOT renumbered by the 2022 modernization (that covered spirits and
malt beverages only), so wine citations use the original section numbers. The
distinctive wine rules versus spirits:

  - Standards of fill are a DIFFERENT list (27 CFR 4.72), expanded January 2025.
  - Alcohol content has a "table wine"/"light wine" exception (27 CFR 4.36): a
    wine of 14% or less may omit the numeric percentage if it is designated
    "table" or "light" wine.
  - An appellation of origin is conditionally mandatory (27 CFR 4.34(b)) when the
    wine is labeled with a grape varietal or a vintage date.
  - A sulfite declaration is required at 10 ppm or more (27 CFR 4.32(e)); the ppm
    trigger cannot be proven from a photo, so this is advisory, never a hard gate.

The Government Warning (27 CFR Part 16) is shared with every beverage.
"""
import re

from . import warning
from .base import FAIL, PASS, REVIEW, RuleOutcome
from .fill import parse_ml

# Authorized metric standards of fill for wine (mL), 27 CFR 4.72, including the
# January 2025 additions (T.D. TTB-203). Containers over 3 L are allowed in whole
# ("even") liter amounts, and containers of 18 L or more are exempt.
AUTHORIZED_ML = {
    3000, 2250, 1800, 1500, 1000, 750, 720, 700, 620, 600, 568, 550, 500, 473,
    375, 360, 355, 330, 300, 250, 200, 187, 180, 100, 50,
}
LARGE_FORMAT_EXEMPT_ML = 18000  # 18 L and above: standards of fill do not apply.

# Recognized wine class/type designations and common grape varietals (lowercased).
RECOGNIZED = {
    "red wine", "white wine", "rose wine", "rosé wine", "pink wine", "blush wine",
    "table wine", "light wine", "dessert wine", "sparkling wine", "carbonated wine",
    "champagne", "crackling wine", "petillant", "frizzante", "fruit wine",
    "aperitif wine", "vermouth", "sherry", "port", "madeira", "muscatel", "angelica",
    "retsina", "sangria", "mead", "burgundy", "chablis", "chianti", "sauterne",
    "rhine wine", "moselle", "claret", "marsala", "tokay",
    # Common varietals (a varietal name is itself a valid designation).
    "cabernet", "merlot", "chardonnay", "pinot", "zinfandel", "riesling",
    "sauvignon", "syrah", "shiraz", "malbec", "grenache", "tempranillo",
    "sangiovese", "gewurztraminer", "gewürztraminer", "viognier", "moscato",
    "prosecco", "cava", "gruner", "barbera", "nebbiolo",
}

_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent)")
_ALCVOL = re.compile(r"alc|vol")


def _percent_value(text: str | None) -> float | None:
    if not text:
        return None
    m = _PERCENT.search(text.lower())
    return float(m.group(1)) if m else None


def _missing(value) -> bool:
    return not value or (isinstance(value, str) and not value.strip())


def check_presence(fields) -> RuleOutcome:
    """Always-mandatory elements (27 CFR 4.32). Alcohol content is handled in its
    own rule because it is conditional on the table-wine exception."""
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
        return RuleOutcome("Mandatory fields", PASS, "All mandatory elements are present.", "27 CFR 4.32")
    listed = ", ".join(missing)
    if not fields.overall_legible:
        return RuleOutcome("Mandatory fields", REVIEW, f"Could not find: {listed}. The image was not clearly readable, so review by hand.", "27 CFR 4.32")
    return RuleOutcome("Mandatory fields", FAIL, f"Missing mandatory element(s): {listed}.", "27 CFR 4.32", {"missing": missing})


def check_classtype(fields) -> RuleOutcome:
    """Recognized wine designation or varietal (27 CFR 4.21, 4.34)."""
    raw = fields.class_type
    if _missing(raw):
        if not _missing(fields.grape_varietal):
            return RuleOutcome("Class/type", PASS, f"Varietal designation '{fields.grape_varietal}'.", "27 CFR 4.34")
        return RuleOutcome("Class/type", REVIEW, "Class/type not found; see the mandatory-fields check.", "27 CFR 4.34")
    low = raw.lower()
    if any(term in low for term in RECOGNIZED) or not _missing(fields.grape_varietal):
        return RuleOutcome("Class/type", PASS, f"'{raw}' is a recognized wine designation.", "27 CFR 4.21")
    return RuleOutcome("Class/type", REVIEW, f"'{raw}' is not a recognized wine designation. It may be a statement of composition; a human should confirm.", "27 CFR 4.34")


def check_abv(fields) -> RuleOutcome:
    """Alcohol content with the table/light exception (27 CFR 4.36).

    Numeric % alc by volume is mandatory, EXCEPT a wine of 14% or less may omit it
    when designated 'table wine' or 'light wine'.
    """
    raw = fields.alcohol_content
    low_class = (fields.class_type or "").lower()
    table_or_light = "table" in low_class or "light" in low_class

    value = _percent_value(raw)
    has_alcvol = bool(_ALCVOL.search(raw.lower())) if raw else False

    if value is not None:
        # A numeric statement is present. Stating it is always allowed.
        if has_alcvol:
            return RuleOutcome("Alcohol content", PASS, f"States {value}% alcohol by volume.", "27 CFR 4.36")
        return RuleOutcome("Alcohol content", REVIEW, f"A percentage is shown but not clearly labeled as alcohol by volume in '{raw}'. Verify by hand.", "27 CFR 4.36")

    # No numeric percentage read.
    if table_or_light:
        return RuleOutcome("Alcohol content", PASS, "Designated table/light wine (14% or less), so the numeric percentage may be omitted.", "27 CFR 4.36")
    if not fields.overall_legible:
        return RuleOutcome("Alcohol content", REVIEW, "No alcohol statement read and the image was not clearly readable. Review by hand.", "27 CFR 4.36")
    return RuleOutcome("Alcohol content", FAIL, "No alcohol by volume statement found. Wine must state it unless designated 'table' or 'light' wine.", "27 CFR 4.36")


def check_fill(fields) -> RuleOutcome:
    """Net contents against wine standards of fill (27 CFR 4.72)."""
    raw = fields.net_contents
    if _missing(raw):
        return RuleOutcome("Net contents", REVIEW, "Net contents not found; see the mandatory-fields check.", "27 CFR 4.72")
    ml = parse_ml(raw)
    if ml is None:
        return RuleOutcome("Net contents", REVIEW, f"Could not read a metric volume from '{raw}'. Verify by hand.", "27 CFR 4.72")
    if ml >= LARGE_FORMAT_EXEMPT_ML:
        return RuleOutcome("Net contents", PASS, f"{raw} (18 L or more) is exempt from standards of fill.", "27 CFR 4.72")
    if ml > 3000:
        if abs(ml - round(ml / 1000) * 1000) < 0.5:
            return RuleOutcome("Net contents", PASS, f"{raw} is a whole-liter size over 3 L, which is authorized.", "27 CFR 4.72")
        return RuleOutcome("Net contents", FAIL, f"{raw} ({ml:.0f} mL) is over 3 L but not a whole-liter size.", "27 CFR 4.72")
    if any(abs(ml - size) < 0.5 for size in AUTHORIZED_ML):
        return RuleOutcome("Net contents", PASS, f"{raw} is an authorized standard of fill.", "27 CFR 4.72")
    return RuleOutcome("Net contents", FAIL, f"{raw} ({ml:.0f} mL) is not an authorized wine standard of fill.", "27 CFR 4.72", {"authorized_ml": sorted(AUTHORIZED_ML, reverse=True)})


def check_appellation(fields) -> RuleOutcome:
    """Appellation is conditionally mandatory (27 CFR 4.34(b)) when a varietal or
    vintage is shown."""
    triggered_by = []
    if not _missing(fields.grape_varietal):
        triggered_by.append("a grape varietal")
    if not _missing(fields.vintage):
        triggered_by.append("a vintage date")

    if not triggered_by:
        return RuleOutcome("Appellation", PASS, "No appellation is required for this designation.", "27 CFR 4.34")
    reason_trigger = " and ".join(triggered_by)
    if not _missing(fields.appellation):
        return RuleOutcome("Appellation", PASS, f"Appellation '{fields.appellation}' is shown, as required by {reason_trigger}.", "27 CFR 4.34")
    if not fields.overall_legible:
        return RuleOutcome("Appellation", REVIEW, f"{reason_trigger} is shown but no appellation was read, and the image was unclear. Review by hand.", "27 CFR 4.34")
    return RuleOutcome("Appellation", REVIEW, f"{reason_trigger.capitalize()} is shown, which requires an appellation of origin, but none was read. Confirm by hand.", "27 CFR 4.34")


def check_sulfite(fields) -> RuleOutcome:
    """Sulfite declaration (27 CFR 4.32(e)). Advisory: the 10 ppm trigger cannot be
    proven from a photo, so this never changes the verdict (golden=False)."""
    advisory = {"tier2_advisory": "A 'Contains Sulfites' declaration is required at 10 ppm or more (27 CFR 4.32(e)). The ppm level cannot be read from a photo, so confirm against lab data."}
    if not _missing(fields.sulfite_statement):
        return RuleOutcome("Sulfite declaration", PASS, f"'{fields.sulfite_statement}' is present.", "27 CFR 4.32(e)", advisory, golden=False)
    return RuleOutcome("Sulfite declaration", REVIEW, "No sulfite declaration was read. Most wines need 'Contains Sulfites'; confirm by hand (advisory, does not change the verdict).", "27 CFR 4.32(e)", advisory, golden=False)


def run(fields) -> list[RuleOutcome]:
    """Apply all wine rules in label-reading order."""
    return [
        check_presence(fields),
        check_classtype(fields),
        check_abv(fields),
        check_fill(fields),
        check_appellation(fields),
        check_sulfite(fields),
        warning.check(fields),
    ]
