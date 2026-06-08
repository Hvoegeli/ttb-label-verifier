"""The labeled mutant corpus: known-answer test labels for the rule engine.

Each case starts from one compliant baseline label and applies a SINGLE, named
mutation (a planted violation or an alternate-but-valid value). Because only one
thing changes per case, a wrong verdict points straight at the rule responsible,
which makes failures easy to diagnose.

Ground truth here means: a human read the regulation, decided what the verdict
SHOULD be, and wrote it down next to the mutation. The eval then proves the code
reproduces that human judgment for every case.

Field names used in `expected_fields` are the human-readable labels the rules
emit (RuleOutcome.field):
    "Mandatory fields"  -> presence.py   (27 CFR 5.63)
    "Class/type"        -> classtype.py  (27 CFR 5.141-5.143)
    "Alcohol content"   -> abv.py        (27 CFR 5.65)
    "Net contents"      -> fill.py       (27 CFR 5.203)
    "Government warning" -> warning.py    (27 CFR 16.21 / 16.22)
"""
from dataclasses import dataclass, field

from app.rules import FAIL, PASS, REVIEW
from app.rules.warning import CANONICAL

# A fully compliant distilled-spirits label. Every case is this, minus one change.
BASELINE = dict(
    brand_name="OLD TOM DISTILLERY",
    class_type="Kentucky Straight Bourbon Whiskey",
    alcohol_content="45% Alc./Vol. (90 Proof)",
    net_contents="750 mL",
    name_and_address="Bottled by Old Tom Distillery, Bardstown, KY",
    government_warning=CANONICAL,
    warning_legible=True,
    overall_legible=True,
)


def _label(**overrides):
    """Build a label dict from the baseline with the given fields overridden."""
    data = dict(BASELINE)
    data.update(overrides)
    return data


@dataclass(frozen=True)
class EvalCase:
    id: str                         # short stable identifier
    category: str                   # which rule / behavior this probes
    description: str                # the planted mutation, in plain language
    fields: dict                    # the full label as extracted-field values
    expected_overall: str           # PASS | FAIL | NEEDS REVIEW
    expected_fields: dict = field(default_factory=dict)  # field name -> expected status


# Warning mutants are derived from the single canonical text so they can never
# drift away from what the rule actually compares against.
_WARNING_TITLE_CASE = CANONICAL.replace("GOVERNMENT WARNING", "Government Warning")
_WARNING_NO_SENTENCE_2 = CANONICAL.split(" (2)")[0]
_WARNING_ALTERED = CANONICAL.replace("health problems.", "health issues.")
_WARNING_EXTRA_SPACES = "  " + CANONICAL.replace(" ", "  ")
_WARNING_GARBLED = "G0VERNMENT W@RN1NG (1) Acc0rding to the Surge0n Genera1 ... [blurry]"
_WARNING_LOWERCASE = CANONICAL.lower()
_WARNING_NO_COLON = CANONICAL.replace("GOVERNMENT WARNING:", "GOVERNMENT WARNING")
_WARNING_NO_SENTENCE_1 = "GOVERNMENT WARNING: (2)" + CANONICAL.split(" (2)")[1]


CASES = [
    # --- Fully compliant variants (expected PASS) ---
    EvalCase(
        "compliant-baseline", "compliant",
        "A correct bourbon label; nothing wrong.",
        _label(),
        PASS,
    ),
    EvalCase(
        "compliant-vodka-1750", "compliant",
        "A different but valid spirit: vodka, 40% Alc/Vol, 1.75 L.",
        _label(class_type="Vodka", alcohol_content="40% Alc/Vol", net_contents="1.75 L"),
        PASS,
    ),
    EvalCase(
        "compliant-brand-fallback", "compliant",
        "No separate brand name, but a name/address statement stands in (5.64(a)).",
        _label(brand_name=None),
        PASS,
        {"Mandatory fields": PASS},
    ),
    EvalCase(
        "compliant-min-fill-50ml", "compliant",
        "Smallest authorized size, 50 mL miniature.",
        _label(net_contents="50 mL"),
        PASS,
        {"Net contents": PASS},
    ),
    EvalCase(
        "compliant-warning-extra-whitespace", "compliant",
        "Warning is verbatim but padded with extra spaces; whitespace is ignored.",
        _label(government_warning=_WARNING_EXTRA_SPACES),
        PASS,
        {"Government warning": PASS},
    ),
    EvalCase(
        "compliant-warning-all-caps", "compliant",
        "Warning printed entirely in capital letters, as real bottles do; compliant.",
        _label(government_warning=CANONICAL.upper()),
        PASS,
        {"Government warning": PASS},
    ),
    EvalCase(
        "compliant-abv-percent-only", "compliant",
        "Alcohol stated as percent by volume with no proof; proof is optional.",
        _label(alcohol_content="45% Alc./Vol."),
        PASS,
        {"Alcohol content": PASS},
    ),
    EvalCase(
        "compliant-gin", "compliant",
        "London Dry Gin, a recognized class/type designation.",
        _label(class_type="London Dry Gin"),
        PASS,
        {"Class/type": PASS},
    ),

    # --- Government warning violations (27 CFR 16.21 / 16.22) ---
    EvalCase(
        "warning-title-case", "warning",
        "'GOVERNMENT WARNING' rendered in title case instead of capitals.",
        _label(government_warning=_WARNING_TITLE_CASE),
        FAIL,
        {"Government warning": FAIL},
    ),
    EvalCase(
        "warning-missing-sentence-2", "warning",
        "The second required sentence (drive/operate machinery) is dropped.",
        _label(government_warning=_WARNING_NO_SENTENCE_2),
        FAIL,
        {"Government warning": FAIL},
    ),
    EvalCase(
        "warning-altered-wording", "warning",
        "'health problems' changed to 'health issues' -- not verbatim.",
        _label(government_warning=_WARNING_ALTERED),
        FAIL,
        {"Government warning": FAIL},
    ),
    EvalCase(
        "warning-missing-legible", "warning",
        "No warning at all on an otherwise clearly readable label.",
        _label(government_warning=None),
        FAIL,
        {"Government warning": FAIL},
    ),
    EvalCase(
        "warning-garbled-illegible", "warning",
        "Warning present but unreadable and flagged illegible -> human review, not a fail.",
        _label(government_warning=_WARNING_GARBLED, warning_legible=False),
        REVIEW,
        {"Government warning": REVIEW},
    ),

    # --- Standards of fill (27 CFR 5.203) ---
    EvalCase(
        "fill-offlist-800ml", "fill",
        "800 mL is not an authorized standard of fill.",
        _label(net_contents="800 mL"),
        FAIL,
        {"Net contents": FAIL},
    ),
    EvalCase(
        "fill-offlist-1600ml", "fill",
        "1.6 L is not an authorized standard of fill.",
        _label(net_contents="1.6 L"),
        FAIL,
        {"Net contents": FAIL},
    ),
    EvalCase(
        "fill-unparseable", "fill",
        "Net contents present but not a readable metric volume -> review.",
        _label(net_contents="one bottle"),
        REVIEW,
        {"Net contents": REVIEW},
    ),

    # --- Alcohol content (27 CFR 5.65) ---
    EvalCase(
        "abv-proof-alone", "abv",
        "Only proof is stated; percent alcohol by volume is mandatory.",
        _label(alcohol_content="90 Proof"),
        FAIL,
        {"Alcohol content": FAIL},
    ),
    EvalCase(
        "abv-bare-percent", "abv",
        "A bare percentage not labeled as alcohol by volume -> review.",
        _label(alcohol_content="45%"),
        REVIEW,
        {"Alcohol content": REVIEW},
    ),

    # --- Class/type (27 CFR 5.141-5.143) ---
    EvalCase(
        "classtype-unrecognized", "classtype",
        "An invented designation a human should confirm -> review.",
        _label(class_type="Mystery Elixir"),
        REVIEW,
        {"Class/type": REVIEW},
    ),

    # --- Mandatory presence (27 CFR 5.63) ---
    EvalCase(
        "presence-missing-net-contents", "presence",
        "Net contents missing entirely -> a mandatory field is absent.",
        _label(net_contents=None),
        FAIL,
        {"Mandatory fields": FAIL},
    ),
    EvalCase(
        "presence-no-brand-no-name", "presence",
        "Neither a brand name nor a name/address statement -> nothing to identify it.",
        _label(brand_name=None, name_and_address=None),
        FAIL,
        {"Mandatory fields": FAIL},
    ),
    EvalCase(
        "presence-missing-when-illegible", "presence",
        "Class/type missing AND the image was not clearly readable -> review, not fail.",
        _label(class_type=None, overall_legible=False),
        REVIEW,
        {"Mandatory fields": REVIEW, "Class/type": REVIEW},
    ),

    # --- Confidence gate and aggregation ---
    EvalCase(
        "illegible-overall", "aggregation",
        "Every field looks valid but the whole image was flagged unreadable -> review.",
        _label(overall_legible=False),
        REVIEW,
    ),
    EvalCase(
        "multi-fail-beats-review", "aggregation",
        "An illegal fill size (FAIL) plus an unrecognized class/type (REVIEW); FAIL wins.",
        _label(net_contents="800 mL", class_type="Mystery Elixir"),
        FAIL,
        {"Net contents": FAIL, "Class/type": REVIEW},
    ),

    # === Expansion to ~50 cases ===

    # --- More compliant spirit types and valid formats (PASS) ---
    EvalCase(
        "compliant-rum-700", "compliant",
        "Aged Rum at 700 mL, an authorized 2020 standard of fill.",
        _label(class_type="Aged Rum", net_contents="700 mL"),
        PASS,
        {"Net contents": PASS, "Class/type": PASS},
    ),
    EvalCase(
        "compliant-tequila-1L", "compliant",
        "Tequila at 1.0 L.",
        _label(class_type="Tequila", net_contents="1.0 L"),
        PASS,
    ),
    EvalCase(
        "compliant-rye-375", "compliant",
        "Straight Rye Whiskey at 375 mL.",
        _label(class_type="Straight Rye Whiskey", net_contents="375 mL"),
        PASS,
    ),
    EvalCase(
        "compliant-scotch-whisky-spelling", "compliant",
        "Single Malt Scotch Whisky (the 'whisky' spelling is recognized).",
        _label(class_type="Single Malt Scotch Whisky"),
        PASS,
        {"Class/type": PASS},
    ),
    EvalCase(
        "compliant-net-1800", "compliant",
        "1.8 L, an authorized January 2025 standard of fill.",
        _label(net_contents="1.8 L"),
        PASS,
        {"Net contents": PASS},
    ),
    EvalCase(
        "compliant-net-centiliters", "compliant",
        "Net contents stated in centiliters (70 cl = 700 mL).",
        _label(net_contents="70 cl"),
        PASS,
        {"Net contents": PASS},
    ),
    EvalCase(
        "compliant-abv-percent-spelled", "compliant",
        "Alcohol stated as '40 percent alcohol by volume' (word form).",
        _label(alcohol_content="40 percent alcohol by volume"),
        PASS,
        {"Alcohol content": PASS},
    ),
    EvalCase(
        "compliant-abv-decimal", "compliant",
        "Decimal ABV value, 43.5% Alc./Vol.",
        _label(alcohol_content="43.5% Alc./Vol."),
        PASS,
        {"Alcohol content": PASS},
    ),

    # --- More standards of fill (27 CFR 5.203) ---
    EvalCase(
        "fill-offlist-400ml", "fill",
        "400 mL is not an authorized standard of fill.",
        _label(net_contents="400 mL"),
        FAIL,
        {"Net contents": FAIL},
    ),
    EvalCase(
        "fill-offlist-1500ml", "fill",
        "1.5 L is not an authorized standard of fill.",
        _label(net_contents="1.5 L"),
        FAIL,
        {"Net contents": FAIL},
    ),
    EvalCase(
        "fill-offlist-650ml", "fill",
        "650 mL is not an authorized standard of fill.",
        _label(net_contents="650 mL"),
        FAIL,
        {"Net contents": FAIL},
    ),
    EvalCase(
        "fill-pass-570ml", "fill",
        "570 mL is an authorized (less common) size.",
        _label(net_contents="570 mL"),
        PASS,
        {"Net contents": PASS},
    ),
    EvalCase(
        "fill-pass-945ml", "fill",
        "945 mL is an authorized size.",
        _label(net_contents="945 mL"),
        PASS,
        {"Net contents": PASS},
    ),
    EvalCase(
        "fill-nonmetric-only", "fill",
        "Only US customary units given (25.4 oz), no metric volume to validate -> review.",
        _label(net_contents="25.4 oz"),
        REVIEW,
        {"Net contents": REVIEW},
    ),

    # --- More alcohol content (27 CFR 5.65) ---
    EvalCase(
        "abv-words-only", "abv",
        "'cask strength' with no percentage or proof -> review.",
        _label(alcohol_content="cask strength"),
        REVIEW,
        {"Alcohol content": REVIEW},
    ),
    EvalCase(
        "abv-alcvol-no-number", "abv",
        "'alcohol by volume' with no number -> cannot confirm -> review.",
        _label(alcohol_content="alcohol by volume"),
        REVIEW,
        {"Alcohol content": REVIEW},
    ),
    EvalCase(
        "abv-proof-only-151", "abv",
        "'151 Proof' alone; percent by volume is mandatory.",
        _label(alcohol_content="151 Proof"),
        FAIL,
        {"Alcohol content": FAIL},
    ),
    EvalCase(
        "abv-abbreviation-only", "abv",
        "'40% ABV' uses the abbreviation, not explicit 'alc/vol' -> review (known limitation).",
        _label(alcohol_content="40% ABV"),
        REVIEW,
        {"Alcohol content": REVIEW},
    ),

    # --- More class/type (27 CFR 5.141-5.143) ---
    EvalCase(
        "classtype-aquavit", "classtype",
        "Aquavit is a recognized designation.",
        _label(class_type="Aquavit"),
        PASS,
        {"Class/type": PASS},
    ),
    EvalCase(
        "classtype-cordial", "classtype",
        "Cherry Cordial; 'cordial' is recognized.",
        _label(class_type="Cherry Cordial"),
        PASS,
        {"Class/type": PASS},
    ),
    EvalCase(
        "classtype-unrecognized-2", "classtype",
        "'Sparkle Juice' is not a standard-of-identity term -> review.",
        _label(class_type="Sparkle Juice"),
        REVIEW,
        {"Class/type": REVIEW},
    ),

    # --- More mandatory presence (27 CFR 5.63) ---
    EvalCase(
        "presence-missing-alcohol", "presence",
        "Alcohol content missing entirely -> a mandatory field is absent.",
        _label(alcohol_content=None),
        FAIL,
        {"Mandatory fields": FAIL},
    ),
    EvalCase(
        "presence-missing-classtype-legible", "presence",
        "Class/type missing on a clearly readable label -> fail (not a read error).",
        _label(class_type=None),
        FAIL,
        {"Mandatory fields": FAIL},
    ),
    EvalCase(
        "presence-missing-name-address", "presence",
        "Name and address missing though a brand name is present -> still a missing mandatory field.",
        _label(name_and_address=None),
        FAIL,
        {"Mandatory fields": FAIL},
    ),

    # --- More government warning (27 CFR 16.21 / 16.22) ---
    EvalCase(
        "warning-missing-sentence-1", "warning",
        "The first required sentence (pregnancy) is dropped.",
        _label(government_warning=_WARNING_NO_SENTENCE_1),
        FAIL,
        {"Government warning": FAIL},
    ),
    EvalCase(
        "warning-all-lowercase", "warning",
        "Entire warning lowercased, so 'GOVERNMENT WARNING' is not in capitals.",
        _label(government_warning=_WARNING_LOWERCASE),
        FAIL,
        {"Government warning": FAIL},
    ),
    EvalCase(
        "warning-missing-colon", "warning",
        "Colon after 'GOVERNMENT WARNING' removed -> not verbatim.",
        _label(government_warning=_WARNING_NO_COLON),
        FAIL,
        {"Government warning": FAIL},
    ),

    # --- More aggregation ---
    EvalCase(
        "review-only-two-fields", "aggregation",
        "Two independent review triggers (unrecognized class + ABV abbreviation), no FAIL -> review.",
        _label(class_type="Sparkle Juice", alcohol_content="40% ABV"),
        REVIEW,
        {"Class/type": REVIEW, "Alcohol content": REVIEW},
    ),
    EvalCase(
        "two-fails", "aggregation",
        "A lowercased warning (FAIL) plus an illegal fill size (FAIL).",
        _label(government_warning=_WARNING_LOWERCASE, net_contents="800 mL"),
        FAIL,
        {"Government warning": FAIL, "Net contents": FAIL},
    ),
]
