"""Vision extraction: one Claude call turns a label image into structured fields.

Design boundary (see docs/MEMO.md decision 2): the model's ONLY job is to read
the printed text off the label into typed fields. It never decides PASS or FAIL.
That keeps the model out of the trust boundary and means a hijacked or mistaken
extraction can never forge a compliant verdict, because the deterministic rule
engine (Task Group 4) makes every decision.

We force structured output with a single tool plus tool_choice, so the model must
return the fields as a JSON object rather than prose we would have to parse.
"""
import base64
from collections.abc import Sequence
from dataclasses import dataclass

import anthropic

from . import costs
from .config import settings
from .models import ExtractedFields  # re-exported for callers/tests
from .rules.base import normalize_ws
from .rules.warning import CANONICAL

# Cap output: the JSON is small, so a low ceiling saves tokens and prevents a
# runaway response from eating the budget.
MAX_TOKENS = 1024


@dataclass
class ExtractionResult:
    """The extracted fields plus the measured cost of producing them."""

    fields: ExtractedFields
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str = ""          # the model whose result this is (or "primary+escalation")
    escalated: bool = False  # whether a low-confidence read triggered a stronger re-read


class ExtractionError(Exception):
    """Raised when the vision service fails or returns no structured fields.

    Carries a message safe to show the user.
    """


# Base fields read from every beverage label.
_BASE_PROPERTIES = {
    "beverage_type": {"type": "string", "enum": ["spirits", "wine", "beer"], "description": "Classify the beverage from the label. 'spirits' for distilled spirits (whiskey, bourbon, vodka, gin, rum, tequila, brandy, cordials/liqueurs). 'wine' for grape or fruit wine, still or sparkling (Cabernet, Chardonnay, Champagne, port, etc.). 'beer' for malt beverages (beer, ale, lager, IPA, stout, porter, and hard seltzers/flavored malt beverages). Pick the single best fit from the class/type and overall design."},
    "brand_name": {"type": ["string", "null"], "description": "The brand name on the label, or null if absent."},
    "class_type": {"type": ["string", "null"], "description": "The class/type designation, e.g. 'Kentucky Straight Bourbon Whiskey', 'Cabernet Sauvignon', or 'India Pale Ale'; null if absent."},
    "alcohol_content": {"type": ["string", "null"], "description": "The alcohol content statement exactly as printed, e.g. '45% Alc./Vol. (90 Proof)' or '13.5% Alc/Vol', or null."},
    "net_contents": {"type": ["string", "null"], "description": "The net contents exactly as printed, e.g. '750 mL' or '12 FL OZ', or null."},
    "name_and_address": {"type": ["string", "null"], "description": "The bottler/producer/importer name and address, or null."},
    "country_of_origin": {"type": ["string", "null"], "description": "The country-of-origin statement exactly as printed, e.g. 'Product of Scotland', 'Product of France', or 'Imported from Mexico'. This is a stated origin for the product itself, NOT the city in the bottler/importer address. Null if no country of origin is stated."},
    "appears_imported": {"type": ["boolean", "null"], "description": "true if the label shows import indicators (an 'imported by' statement, a foreign producer/bottler address, or a stated country of origin); false if it appears domestically produced (e.g. a U.S. bottler address with no import language); null if unclear."},
    "government_warning": {
        "type": ["string", "null"],
        "description": "Transcribe the GOVERNMENT WARNING statement EXACTLY as printed, character for character, preserving capitalization and punctuation. Do not correct or complete it. Null if no warning appears.",
    },
    "warning_legible": {"type": "boolean", "description": "true if the warning text could be read clearly and completely; false if any part was blurry, cut off, or unreadable."},
    "overall_legible": {"type": "boolean", "description": "true if the label image was clear enough to read the fields confidently; false if it was too blurry, dark, angled, or glare-covered."},
}

# Extra fields read only for specific beverages (merged into the universal schema).
_EXTRA_PROPERTIES = {
    "wine": {
        "appellation": {"type": ["string", "null"], "description": "The appellation of origin claimed for the wine (where the grapes are from), e.g. 'Napa Valley' or 'Sonoma Coast', usually shown near the brand or varietal. Record it ONLY if it appears as a stated origin claim for the wine. Do NOT infer it from the city in the producer/bottler address (a bottler located in Napa is not an appellation claim). Null if no appellation is stated."},
        "vintage": {"type": ["string", "null"], "description": "The vintage year if shown, e.g. '2019', or null."},
        "grape_varietal": {"type": ["string", "null"], "description": "The grape varietal if shown, e.g. 'Cabernet Sauvignon', or null."},
        "sulfite_statement": {"type": ["string", "null"], "description": "The sulfite declaration exactly as printed, e.g. 'Contains Sulfites', or null."},
    },
    "beer": {
        "is_flavored_malt_beverage": {"type": ["boolean", "null"], "description": "true if this is a flavored malt beverage (a hard seltzer or beer with added flavors, e.g. fruit or spirit flavoring), false if an ordinary beer/ale/lager, null if unclear."},
        "statement_of_composition": {"type": ["string", "null"], "description": "Any statement of composition describing how it was made or flavored, e.g. 'ale with natural flavors', or null."},
    },
}

# Wine-specific guidance always included now that one universal read serves every
# beverage: the model classifies the type itself, so it must know the wine rules.
_WINE_GUIDANCE = (
    " For the appellation field (wine only): an appellation of origin is a "
    "grape-growing region CLAIMED for the wine, such as 'Napa Valley', 'Sonoma "
    "Coast', or 'Willamette Valley', usually shown near the brand or the varietal. "
    "The city inside the producer or bottler address line is NOT an appellation: for "
    "example in 'Produced and bottled by Stonecrest Cellars, Napa, CA', the 'Napa' is "
    "just the bottler's location, so appellation must be null unless a region is "
    "separately claimed for the wine itself."
)

# One universal schema reads every beverage's fields plus the detected type, so a
# single call serves a mixed batch without the caller pre-selecting a type.
_UNIVERSAL_PROPERTIES = {**_BASE_PROPERTIES, **_EXTRA_PROPERTIES["wine"], **_EXTRA_PROPERTIES["beer"]}
_UNIVERSAL_REQUIRED = list(_UNIVERSAL_PROPERTIES.keys())


def _build_tool() -> dict:
    """Build the forced-output tool schema (universal: every beverage's fields)."""
    return {
        "name": "record_label_fields",
        "description": "Record the regulated fields read from the alcohol beverage label image.",
        "input_schema": {
            "type": "object",
            "properties": _UNIVERSAL_PROPERTIES,
            "required": _UNIVERSAL_REQUIRED,
        },
    }


def _build_prompt() -> str:
    return (
        "You are reading a U.S. alcohol beverage label from one or more photos of the "
        "same container (for example the front and the back). Read the printed text across "
        "all of the images and record each requested field by calling record_label_fields. "
        "First decide the beverage_type: distilled spirits, wine, or a malt beverage (beer); "
        "judge from the class/type wording and the overall design. Then read the fields; "
        "those that do not apply to this beverage (for example grape varietal on a whiskey) "
        "should be null. "
        "The mandatory information is often split across faces: the government warning, net "
        "contents, and bottler name and address are usually on the back. "
        "Transcribe exactly what is printed; do not infer, correct, complete, or judge "
        "compliance. For the government warning, copy it verbatim, character for character. "
        "For country of origin, record any stated origin for the product (for example "
        "'Product of Scotland'); the city inside a bottler or importer address is NOT a "
        "country of origin. Set appears_imported true when the label carries an 'imported "
        "by' statement, a foreign producer or bottler address, or a stated country of origin. "
        "If a field is not present on any image, use null. If the images are too unclear to "
        "read a field confidently, set the legibility flags to false rather than guessing."
        + _WINE_GUIDANCE
    )

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Lazily build and reuse one client (so the connection pool is shared)."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
    return _client


def _extract_once(images: Sequence[bytes], model: str) -> ExtractionResult:
    """One vision call with a specific model. Raises ExtractionError on failure.

    The schema is universal (every beverage's fields plus the detected
    beverage_type), so no beverage needs to be known before the read.
    """
    image_blocks = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.standard_b64encode(b).decode("ascii"),
            },
        }
        for b in images
    ]

    tool = _build_tool()
    try:
        response = _get_client().messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{
                "role": "user",
                "content": [*image_blocks, {"type": "text", "text": _build_prompt()}],
            }],
        )
    except anthropic.APIError as exc:
        # Covers auth, rate-limit, connection, and server errors. The rule engine
        # is unaffected; we surface a clean message and let the caller route to review.
        raise ExtractionError("The label-reading service was unavailable. Please try again.") from exc

    tool_use = next((block for block in response.content if block.type == "tool_use"), None)
    if tool_use is None:
        raise ExtractionError("The label could not be read into structured fields. Please review by hand.")

    try:
        fields = ExtractedFields(**tool_use.input)
    except Exception as exc:  # pydantic validation or unexpected shape
        raise ExtractionError("The label reading came back in an unexpected format. Please review by hand.") from exc

    usage = response.usage
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    return ExtractionResult(
        fields=fields,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=costs.cost_usd(model, input_tokens, output_tokens),
        model=model,
    )


def _should_escalate(fields: ExtractedFields) -> bool:
    """Whether a low-confidence or likely-misread first pass warrants a stronger re-read.

    Two triggers, both grounded in the real-photo eval finding that the verbatim
    Government Warning is the weak point:
      1. The model's own legibility flags say the read was poor.
      2. The warning is reported legible but does not match the statute verbatim,
         which is often a misread of a compliant label rather than a real defect.
    """
    if not fields.overall_legible or not fields.warning_legible:
        return True
    gw = fields.government_warning
    if gw and normalize_ws(gw).lower() != normalize_ws(CANONICAL).lower():
        return True
    return False


def extract_fields(images: bytes | Sequence[bytes]) -> ExtractionResult:
    """Read one or more normalized JPEGs of the same container into structured fields.

    Accepts a single image (bytes) or several (e.g. the front and back of one
    bottle, whose mandatory fields are split across faces). All images go in one
    call, so the model reconciles them and we pay for one extraction. The read is
    universal: the model classifies the beverage type and reads every beverage's
    fields, so the caller does not pre-select a type (see fields.beverage_type).

    Robustness: the cheap default model reads first. If that read is low confidence
    or the warning does not match the statute, re-read once with the stronger
    escalation model and return that, summing the cost. The extra cost is paid only
    on the hard labels that need it. Set ENABLE_ESCALATION=false to disable.

    Raises ExtractionError (message safe to display) on any API failure or if the
    model does not return the forced tool call.
    """
    if isinstance(images, (bytes, bytearray)):
        images = [images]

    primary = settings.claude_model
    result = _extract_once(images, primary)

    esc_model = settings.escalation_model
    if settings.enable_escalation and esc_model and esc_model != primary and _should_escalate(result.fields):
        try:
            escalated = _extract_once(images, esc_model)
        except ExtractionError:
            # Escalation failed (rate limit, etc.): keep the primary read rather than
            # failing the whole label. The rule engine still gets the first pass.
            return result
        return ExtractionResult(
            fields=escalated.fields,
            input_tokens=result.input_tokens + escalated.input_tokens,
            output_tokens=result.output_tokens + escalated.output_tokens,
            cost_usd=result.cost_usd + escalated.cost_usd,
            model=f"{primary}+{esc_model}",
            escalated=True,
        )
    return result
