"""Class/type designation check (27 CFR 5.141 - 5.143).

The label must carry a recognized standard-of-identity designation. The full set
of designations and modifiers is large, so an unrecognized term is treated as
NEEDS REVIEW (a human decides), never an automatic FAIL. This honors the decision
that unrecognized-but-plausible values route to review rather than false failures.
"""
from .base import PASS, REVIEW, RuleOutcome

FIELD = "Class/type"
CITATION = "27 CFR 5.141-5.143"

# Base spirit designations (lowercased). Modifiers like "straight", "blended",
# "Kentucky" attach to these and do not need to be listed separately.
RECOGNIZED = {
    "whisky", "whiskey", "bourbon", "rye", "scotch", "corn whiskey", "malt whiskey",
    "wheat whiskey", "vodka", "gin", "rum", "cachaca", "brandy", "cognac", "armagnac",
    "applejack", "tequila", "mezcal", "liqueur", "cordial", "schnapps", "aquavit",
    "absinthe", "grappa", "neutral spirits", "grain spirits", "spirit whiskey",
    "distilled spirits specialty",
}


def check(fields) -> RuleOutcome:
    raw = fields.class_type
    if not raw or not raw.strip():
        return RuleOutcome(FIELD, REVIEW, "Class/type not found; see the mandatory-fields check.", CITATION)

    low = raw.lower()
    if any(term in low for term in RECOGNIZED):
        return RuleOutcome(FIELD, PASS, f"'{raw}' is a recognized class/type designation.", CITATION)

    return RuleOutcome(
        FIELD, REVIEW,
        f"'{raw}' is not a recognized standard-of-identity term. A human should confirm it.",
        CITATION,
    )
