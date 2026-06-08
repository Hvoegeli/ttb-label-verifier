"""Standards of fill check for distilled spirits (27 CFR 5.203).

The net-contents value must be one of the authorized metric sizes. An off-list
size fails even if the net-contents text is otherwise correct. The metric value
governs; US customary equivalents are not validated against the list here.
"""
import re

from .base import FAIL, PASS, REVIEW, RuleOutcome

FIELD = "Net contents"
CITATION = "27 CFR 5.203"

# Authorized distilled spirits sizes in milliliters, including the 2020 additions
# (700/720 mL etc.) and the January 2025 additions (900 mL, 1.8 L) from T.D. TTB-200.
AUTHORIZED_ML = {
    3750, 3000, 2000, 1800, 1750, 1000, 945, 900, 750, 720, 710, 700, 570,
    500, 475, 375, 355, 350, 331, 250, 200, 187, 100, 50,
}

_QTY = re.compile(r"(\d+(?:\.\d+)?)\s*(ml|millilit\w*|cl|litre|liter|lit\w*|l)\b")


def parse_ml(text: str) -> float | None:
    """Parse a metric net-contents value into milliliters, or None if not found."""
    if not text:
        return None
    low = text.lower().replace(",", "")
    match = _QTY.search(low)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    if unit.startswith("ml") or unit.startswith("millilit"):
        return value
    if unit.startswith("cl"):
        return value * 10
    return value * 1000  # liters


def check(fields) -> RuleOutcome:
    raw = fields.net_contents
    if not raw or not raw.strip():
        # Absence is the presence rule's job; here we just defer.
        return RuleOutcome(FIELD, REVIEW, "Net contents not found; see the mandatory-fields check.", CITATION)

    ml = parse_ml(raw)
    if ml is None:
        return RuleOutcome(FIELD, REVIEW, f"Could not read a metric volume from '{raw}'. Verify by hand.", CITATION)

    if any(abs(ml - size) < 0.5 for size in AUTHORIZED_ML):
        return RuleOutcome(FIELD, PASS, f"{raw} is an authorized standard of fill.", CITATION)

    return RuleOutcome(
        FIELD, FAIL,
        f"{raw} ({ml:.0f} mL) is not an authorized standard of fill.",
        CITATION,
        {"authorized_ml": sorted(AUTHORIZED_ML, reverse=True)},
    )
