"""Eval corpus as parametrized tests -- every known verdict must reproduce.

Each mutant from evals/corpus.py becomes its own test case (named by id), so a
regression in any single rule shows up as one clearly-named failure rather than a
single opaque assertion. No Claude call is made, so this is free and deterministic.
"""
import pytest

from app.models import ExtractedFields
from app.rules import overall_verdict, run_rules

from evals.corpus import CASES


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_known_verdict_reproduces(case):
    fields = ExtractedFields(**case.fields)
    outcomes = run_rules(fields)
    by_field = {o.field: o.status for o in outcomes}

    overall = overall_verdict(outcomes, fields.overall_legible)
    assert overall == case.expected_overall, (
        f"{case.id}: expected overall {case.expected_overall}, got {overall}"
    )

    for name, want in case.expected_fields.items():
        assert by_field.get(name) == want, (
            f"{case.id}: field '{name}' expected {want}, got {by_field.get(name)}"
        )


def test_corpus_is_nontrivial():
    """Guard against an accidentally emptied or all-PASS corpus."""
    assert len(CASES) >= 20
    verdicts = {c.expected_overall for c in CASES}
    assert {"PASS", "FAIL", "NEEDS REVIEW"} <= verdicts
