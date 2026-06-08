"""Match check: extracted label fields vs a mock application (TTB Form 5100.31).

This is the "label vs the form" pass, distinct from the "label vs the law"
compliance check. It resolves the fuzzy-vs-exact tension from the discovery
interviews with field-specific strictness:

  - Brand name, class/type, alcohol content, net contents: compared loosely
    (case, punctuation, and spacing ignored), so "STONE'S THROW" matches
    "Stone's Throw" and "750 mL" matches "750ml". Capitalization does not change
    identity for these designations.
  - Government warning: compared exactly (whitespace normalized only), because
    the statute fixes the words.

Only fields the application actually provides are compared.
"""
import re
from dataclasses import dataclass

from .rules.base import normalize_ws
from .rules.fill import parse_ml

MATCH = "MATCH"
MISMATCH = "MISMATCH"
NA = "N/A"

# Application keys -> (display label, comparison mode). Order is display order.
# loose: ignore case/punctuation/spacing. percent: compare the ABV number.
# volume: compare the metric mL value. exact: whitespace-normalized, case-sensitive.
_FIELDS = [
    ("brand_name", "Brand name", "loose"),
    ("class_type", "Class/type", "loose"),
    ("alcohol_content", "Alcohol content", "percent"),
    ("net_contents", "Net contents", "volume"),
    ("government_warning", "Government warning", "exact"),
]

_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent)")


@dataclass
class MatchOutcome:
    field: str
    label_value: str
    application_value: str
    status: str
    note: str = ""

    def as_row(self) -> dict:
        return {
            "field": self.field,
            "label": self.label_value,
            "application": self.application_value,
            "status": self.status,
            "note": self.note,
            "css": self.status.lower().replace(" ", "-").replace("/", ""),
        }


def _loose(value: str | None) -> str:
    """Collapse to alphanumerics only, lowercased (ignore case/punctuation/spacing)."""
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _percent(value: str | None) -> float | None:
    """First percentage in the string as a float, or None."""
    if not value:
        return None
    m = _PERCENT.search(value.lower())
    return float(m.group(1)) if m else None


def _compare(mode: str, label_val: str, app_val: str) -> bool:
    """Apply the field-specific comparison; fall back to loose if a value won't parse."""
    if mode == "exact":
        return normalize_ws(label_val) == normalize_ws(app_val)
    if mode == "percent":
        lp, ap = _percent(label_val), _percent(app_val)
        if lp is not None and ap is not None:
            return abs(lp - ap) < 0.05
        return _loose(label_val) == _loose(app_val)
    if mode == "volume":
        lv, av = parse_ml(label_val), parse_ml(app_val)
        if lv is not None and av is not None:
            return abs(lv - av) < 0.5
        return _loose(label_val) == _loose(app_val)
    return _loose(label_val) == _loose(app_val)


def compare(fields, application: dict) -> list[MatchOutcome]:
    """Compare extracted fields against the provided application values."""
    outcomes: list[MatchOutcome] = []
    for key, label, mode in _FIELDS:
        if key not in application:
            continue
        app_raw = application[key]
        if app_raw is None or not str(app_raw).strip():
            continue
        app_val = str(app_raw)

        label_raw = getattr(fields, key, None)
        if label_raw is None or not str(label_raw).strip():
            outcomes.append(MatchOutcome(label, "(not found)", app_val, NA, "Label value not found"))
            continue
        label_val = str(label_raw)

        if _compare(mode, label_val, app_val):
            note = ""
            if label_val.strip() != app_val.strip():
                note = "matched on value" if mode in ("percent", "volume") else "matched after normalizing case/punctuation"
            outcomes.append(MatchOutcome(label, label_val, app_val, MATCH, note))
        else:
            outcomes.append(MatchOutcome(label, label_val, app_val, MISMATCH))
    return outcomes
