"""Shared data models, kept separate so pure logic (the rule engine) can import
them without pulling in the Anthropic SDK."""
from pydantic import BaseModel


class ExtractedFields(BaseModel):
    """The regulated fields read off a distilled spirits label.

    Any field the model cannot find is None. The two legibility flags drive the
    confidence gate: a label that could not be read confidently routes to human
    review rather than producing a false verdict.
    """

    brand_name: str | None = None
    class_type: str | None = None
    alcohol_content: str | None = None
    net_contents: str | None = None
    name_and_address: str | None = None
    government_warning: str | None = None
    # True if the warning text was read cleanly; False if partial/blurry/garbled.
    warning_legible: bool = True
    # True if the label overall was clear enough to trust the extraction.
    overall_legible: bool = True
