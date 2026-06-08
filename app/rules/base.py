"""Shared types for the deterministic rule engine.

Every rule is a pure function: it takes the extracted fields and returns a
RuleOutcome. No I/O, no model, no randomness, so the same input always yields
the same verdict and citation. That is what makes the compliance decisions
reproducible and auditable.
"""
from dataclasses import dataclass

# Per-field verdict states.
PASS = "PASS"
FAIL = "FAIL"
REVIEW = "NEEDS REVIEW"


@dataclass
class RuleOutcome:
    field: str          # human-readable field name, e.g. "Government warning"
    status: str         # PASS | FAIL | NEEDS REVIEW
    reason: str         # plain-language explanation
    citation: str       # controlling CFR section
    detail: dict | None = None  # optional extra (diffs, advisory notes, lists)
    # A Golden Rule is a mandatory, image-provable hard gate: any single FAIL
    # fails the whole label. Advisory checks (golden=False) inform a human but
    # never auto-fail. Every mandatory rule in this engine is golden.
    golden: bool = True

    def as_row(self) -> dict:
        """Flatten for template rendering."""
        return {
            "name": self.field,
            "status": self.status,
            "reason": self.reason,
            "citation": self.citation,
            "golden": self.golden,
        }


def normalize_ws(text: str) -> str:
    """Collapse runs of whitespace to single spaces and strip ends.

    This is the ONLY normalization allowed on the government warning: we never
    lowercase or strip punctuation, because the statute fixes both.
    """
    return " ".join(text.split()).strip()
