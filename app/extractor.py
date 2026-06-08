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
from dataclasses import dataclass

import anthropic

from . import costs
from .config import settings
from .models import ExtractedFields  # re-exported for callers/tests

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


class ExtractionError(Exception):
    """Raised when the vision service fails or returns no structured fields.

    Carries a message safe to show the user.
    """


# The single tool the model is forced to call. Its schema IS the output shape.
LABEL_FIELDS_TOOL = {
    "name": "record_label_fields",
    "description": "Record the regulated fields read from the alcohol beverage label image.",
    "input_schema": {
        "type": "object",
        "properties": {
            "brand_name": {"type": ["string", "null"], "description": "The brand name on the label, or null if absent."},
            "class_type": {"type": ["string", "null"], "description": "The class/type designation, e.g. 'Kentucky Straight Bourbon Whiskey', or null."},
            "alcohol_content": {"type": ["string", "null"], "description": "The alcohol content statement exactly as printed, e.g. '45% Alc./Vol. (90 Proof)', or null."},
            "net_contents": {"type": ["string", "null"], "description": "The net contents exactly as printed, e.g. '750 mL', or null."},
            "name_and_address": {"type": ["string", "null"], "description": "The bottler/producer/importer name and address, or null."},
            "government_warning": {
                "type": ["string", "null"],
                "description": "Transcribe the GOVERNMENT WARNING statement EXACTLY as printed, character for character, preserving capitalization and punctuation. Do not correct or complete it. Null if no warning appears.",
            },
            "warning_legible": {"type": "boolean", "description": "true if the warning text could be read clearly and completely; false if any part was blurry, cut off, or unreadable."},
            "overall_legible": {"type": "boolean", "description": "true if the label image was clear enough to read the fields confidently; false if it was too blurry, dark, angled, or glare-covered."},
        },
        "required": [
            "brand_name", "class_type", "alcohol_content", "net_contents",
            "name_and_address", "government_warning", "warning_legible", "overall_legible",
        ],
    },
}

_PROMPT = (
    "You are reading a U.S. distilled spirits label from an image. Read the printed "
    "text and record each requested field by calling record_label_fields. "
    "Transcribe exactly what is printed; do not infer, correct, complete, or judge "
    "compliance. For the government warning, copy it verbatim, character for character. "
    "If a field is not present, use null. If the image is too unclear to read a field "
    "confidently, set the legibility flags to false rather than guessing."
)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Lazily build and reuse one client (so the connection pool is shared)."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
    return _client


def extract_fields(jpeg_bytes: bytes) -> ExtractionResult:
    """Send one normalized JPEG to the model and return the structured fields + cost.

    Raises ExtractionError (message safe to display) on any API failure or if the
    model does not return the forced tool call.
    """
    image_b64 = base64.standard_b64encode(jpeg_bytes).decode("ascii")

    try:
        response = _get_client().messages.create(
            model=settings.claude_model,
            max_tokens=MAX_TOKENS,
            tools=[LABEL_FIELDS_TOOL],
            tool_choice={"type": "tool", "name": LABEL_FIELDS_TOOL["name"]},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                    {"type": "text", "text": _PROMPT},
                ],
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
        cost_usd=costs.cost_usd(settings.claude_model, input_tokens, output_tokens),
    )
