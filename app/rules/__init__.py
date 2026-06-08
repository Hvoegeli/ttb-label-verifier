"""Deterministic rule engine for distilled spirits labels.

run_rules() applies every rule to the extracted fields and returns the per-field
outcomes. overall_verdict() aggregates them with the priority FAIL > NEEDS REVIEW
> PASS, so a clear violation is never masked by an unrelated unreadable field, and
the tool never reports PASS while anything is uncertain.
"""
from . import abv, classtype, fill, presence, warning
from .base import FAIL, PASS, REVIEW, RuleOutcome, normalize_ws

__all__ = ["run_rules", "overall_verdict", "RuleOutcome", "PASS", "FAIL", "REVIEW", "normalize_ws"]


def run_rules(fields) -> list[RuleOutcome]:
    """Apply all distilled-spirits rules, in label-reading order."""
    return [
        presence.check(fields),
        classtype.check(fields),
        abv.check(fields),
        fill.check(fields),
        warning.check(fields),
    ]


def overall_verdict(outcomes: list[RuleOutcome], overall_legible: bool = True) -> str:
    """Aggregate per-field outcomes into one overall verdict.

    Priority: any FAIL -> FAIL; else any NEEDS REVIEW (or an illegible image) ->
    NEEDS REVIEW; else PASS.
    """
    statuses = {o.status for o in outcomes}
    if FAIL in statuses:
        return FAIL
    if REVIEW in statuses or not overall_legible:
        return REVIEW
    return PASS
