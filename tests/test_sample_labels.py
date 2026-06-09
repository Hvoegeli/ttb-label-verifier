"""Ground-truth check for the synthetic sample labels (free, no model call).

Each label in the manifest carries the exact field values printed on it. This
test feeds those fields straight into the real rule engine and asserts the
verdict equals the manifest's "expected". That proves the answer key is correct
per the actual rules, so the paid live eval (evals/sample_eval.py) has a verdict
it can trust to grade the vision read against.
"""
import json
from pathlib import Path

import pytest

from app.models import ExtractedFields
from app.rules import overall_verdict, run_rules

MANIFEST = Path(__file__).resolve().parent.parent / "sample_labels" / "manifest.json"
ENTRIES = json.loads(MANIFEST.read_text())


def test_manifest_size_and_mix():
    # Started at 20 to 25; grew to 27 with two imported-product labels for the
    # country-of-origin check. All three verdicts must be represented.
    assert 20 <= len(ENTRIES) <= 30
    verdicts = {e["expected"] for e in ENTRIES}
    assert verdicts == {"PASS", "FAIL", "NEEDS REVIEW"}


def test_every_image_file_exists():
    for e in ENTRIES:
        path = MANIFEST.parent / e["file"]
        assert path.exists(), f"missing rendered image: {e['file']}"


@pytest.mark.parametrize("entry", ENTRIES, ids=[e["id"] for e in ENTRIES])
def test_declared_fields_produce_expected_verdict(entry):
    # The answer key must match the real rules when given the label's own fields.
    fields = ExtractedFields(**entry["fields"])
    outcomes = run_rules(fields, entry["beverage"])
    overall = overall_verdict(outcomes, fields.overall_legible)
    assert overall == entry["expected"], (
        f"{entry['id']}: rules say {overall}, manifest claims {entry['expected']} "
        f"({entry['planted']})"
    )
