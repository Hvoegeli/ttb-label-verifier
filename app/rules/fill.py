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


def fmt_ml(value: float) -> str:
    """Format a millilitre amount the way a person reads it ('750 mL', '1 L', '1.75 L')."""
    if value >= 1000:
        litres = value / 1000
        return f"{litres:g} L"
    return f"{value:g} mL"


def nearest_sizes(ml: float, authorized: set) -> str:
    """The closest authorized sizes below and above a value, as a plain phrase."""
    below = max((s for s in authorized if s <= ml), default=None)
    above = min((s for s in authorized if s >= ml), default=None)
    parts = []
    if below is not None:
        parts.append(fmt_ml(below))
    if above is not None and above != below:
        parts.append(fmt_ml(above))
    return " and ".join(parts)


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
        return RuleOutcome(FIELD, PASS, f"{raw} is an authorized bottle size.", CITATION)

    reason = f"{raw} is not an authorized bottle size."
    nearest = nearest_sizes(ml, AUTHORIZED_ML)
    if nearest:
        reason += f" The nearest authorized sizes are {nearest}."
    return RuleOutcome(
        FIELD, FAIL, reason, CITATION,
        {"authorized_ml": sorted(AUTHORIZED_ML, reverse=True)},
    )
