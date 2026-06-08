"""Alcohol content format check for distilled spirits (27 CFR 5.65).

Percent alcohol by volume is mandatory. Proof is optional and may appear in
addition, but it can never stand in for the percentage. So "90 Proof" alone is a
FAIL; "45% Alc./Vol." passes; "45% Alc./Vol. (90 Proof)" passes.
"""
import re

from .base import FAIL, PASS, REVIEW, RuleOutcome

FIELD = "Alcohol content"
CITATION = "27 CFR 5.65"

# A number immediately followed by a percent sign or the word "percent".
_PERCENT = re.compile(r"\d+(?:\.\d+)?\s*(?:%|percent)")
_PROOF = re.compile(r"\d+(?:\.\d+)?\s*proof")
# Indicators that the percentage is an alcohol-by-volume statement.
_ALCVOL = re.compile(r"alc|vol")


def check(fields) -> RuleOutcome:
    raw = fields.alcohol_content
    if not raw or not raw.strip():
        return RuleOutcome(FIELD, REVIEW, "Alcohol content not found; see the mandatory-fields check.", CITATION)

    low = raw.lower()
    has_percent = bool(_PERCENT.search(low))
    has_alcvol = bool(_ALCVOL.search(low))
    has_proof = bool(_PROOF.search(low))

    if has_percent and has_alcvol:
        if has_proof:
            return RuleOutcome(FIELD, PASS, "States percent alcohol by volume; proof shown additionally (allowed).", CITATION)
        return RuleOutcome(FIELD, PASS, "States percent alcohol by volume.", CITATION)

    if has_proof and not has_percent:
        return RuleOutcome(
            FIELD, FAIL,
            "Only proof is stated. Percent alcohol by volume is the mandatory statement; proof alone is not sufficient.",
            CITATION,
        )

    if has_percent and not has_alcvol:
        return RuleOutcome(
            FIELD, REVIEW,
            f"A percentage is shown but it is not clearly labeled as alcohol by volume in '{raw}'. Verify by hand.",
            CITATION,
        )

    return RuleOutcome(FIELD, REVIEW, f"Could not confirm a percent-alcohol-by-volume statement in '{raw}'. Verify by hand.", CITATION)
