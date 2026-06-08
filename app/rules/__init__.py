"""Deterministic rule engine, dispatched by beverage type.

Each beverage has its own rule set because the regulations genuinely differ:
distilled spirits (27 CFR Part 5), wine (Part 4), and malt beverages (Part 7).
The Government Warning (Part 16) is the one rule shared by all three.

run_rules(fields, beverage) applies the right set and returns the per-field
outcomes. overall_verdict() aggregates them with the priority FAIL > NEEDS REVIEW
> PASS, considering only Golden Rules (mandatory hard gates); advisory outcomes
(golden=False) are shown to the user but never change the verdict.
"""
from . import abv, beer, classtype, fill, presence, warning, wine
from .base import FAIL, PASS, REVIEW, RuleOutcome, normalize_ws

__all__ = ["run_rules", "overall_verdict", "RuleOutcome", "PASS", "FAIL", "REVIEW", "normalize_ws"]


def _run_spirits(fields) -> list[RuleOutcome]:
    """Distilled spirits rules, in label-reading order (27 CFR Parts 5 and 16)."""
    return [
        presence.check(fields),
        classtype.check(fields),
        abv.check(fields),
        fill.check(fields),
        warning.check(fields),
    ]


_RULESETS = {
    "spirits": _run_spirits,
    "wine": wine.run,
    "beer": beer.run,
}


def run_rules(fields, beverage: str = "spirits") -> list[RuleOutcome]:
    """Apply the rule set for the given beverage (defaults to distilled spirits)."""
    runner = _RULESETS.get(beverage, _run_spirits)
    return runner(fields)


def overall_verdict(outcomes: list[RuleOutcome], overall_legible: bool = True) -> str:
    """Aggregate per-field outcomes into one overall verdict.

    Only Golden Rules (mandatory hard gates) count toward the verdict; advisory
    outcomes are informational. Priority: any FAIL -> FAIL; else any NEEDS REVIEW
    (or an illegible image) -> NEEDS REVIEW; else PASS.
    """
    statuses = {o.status for o in outcomes if getattr(o, "golden", True)}
    if FAIL in statuses:
        return FAIL
    if REVIEW in statuses or not overall_legible:
        return REVIEW
    return PASS
