"""Government Warning check (27 CFR 16.21 / 16.22).

Tier 1 (image-provable, hard pass/fail): the warning must be present and verbatim,
with "GOVERNMENT WARNING" in capital letters. Compared after normalizing whitespace
only, never lowercasing or stripping punctuation.

Tier 2 (cannot verify from a photo): type size in mm, bold weight, contrasting
background, and separate-and-apart placement. Surfaced as an advisory note, never a
FAIL, because a photo carries no physical scale. On a vector PDF these would become
hard checks (production path).
"""
import difflib

from .base import FAIL, PASS, REVIEW, RuleOutcome, normalize_ws

FIELD = "Government warning"
CITATION = "27 CFR 16.21 / 16.22"

# The exact statutory text (Alcoholic Beverage Labeling Act of 1988).
CANONICAL = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)

TIER2_ADVISORY = (
    "Type size (minimum 2 mm for a 750 mL container), bold weight on 'GOVERNMENT "
    "WARNING', contrasting background, and separate-and-apart placement cannot be "
    "verified from a photo (27 CFR 16.22(b)). Verify against print specs."
)


def _explain_difference(want: str, got: str) -> tuple[str, dict]:
    """Produce a human reason plus a small diff for a non-verbatim warning."""
    # Common, specific cases first (clearer than a raw character diff).
    if "(1)" not in got:
        return "The first required sentence is missing or unreadable.", {}
    if "(2)" not in got:
        return "The second required sentence is missing.", {}
    if "GOVERNMENT WARNING" not in got and "government warning" in got.lower():
        return "'GOVERNMENT WARNING' must be in capital letters (27 CFR 16.22).", {}

    # Otherwise, locate the first difference and show a little context.
    matcher = difflib.SequenceMatcher(a=want, b=got, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            expected_near = want[max(0, i1 - 20):i2 + 20]
            got_near = got[max(0, j1 - 20):j2 + 20]
            return (
                "The warning text does not match the required wording.",
                {"expected_near": expected_near, "got_near": got_near},
            )
    return "The warning text does not match the required wording.", {}


def check(fields) -> RuleOutcome:
    raw = fields.government_warning
    detail = {"tier2_advisory": TIER2_ADVISORY}

    if not raw or not raw.strip():
        if not fields.overall_legible or not fields.warning_legible:
            return RuleOutcome(FIELD, REVIEW, "No warning found and the image was not clearly readable. Review by hand.", CITATION, detail)
        return RuleOutcome(FIELD, FAIL, "The Government Warning statement is missing.", CITATION, detail)

    got = normalize_ws(raw)
    want = normalize_ws(CANONICAL)

    if got == want:
        return RuleOutcome(FIELD, PASS, "Present and verbatim.", CITATION, detail)

    # Read but not matching. If the read was shaky, that is a review, not a fail.
    if not fields.warning_legible:
        detail["got"] = got
        return RuleOutcome(FIELD, REVIEW, "The warning could not be read clearly enough to confirm wording. Review by hand.", CITATION, detail)

    # Clean read, but the wording differs -> a real violation.
    reason, diff = _explain_difference(want, got)
    detail.update({"expected": want, "got": got, **diff})
    return RuleOutcome(FIELD, FAIL, reason, CITATION, detail)
