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

    # Wine-specific (27 CFR Part 4); None for other beverages.
    appellation: str | None = None        # appellation of origin, e.g. "Napa Valley"
    vintage: str | None = None            # vintage year if shown
    grape_varietal: str | None = None     # varietal name, e.g. "Cabernet Sauvignon"
    sulfite_statement: str | None = None  # e.g. "Contains Sulfites"

    # Malt beverage / beer-specific (27 CFR Part 7); None for other beverages.
    # True if the label indicates a flavored malt beverage (added nonbeverage
    # flavors), which makes the alcohol statement mandatory; None if unknown.
    is_flavored_malt_beverage: bool | None = None
    statement_of_composition: str | None = None  # §7.147 fallback designation text
