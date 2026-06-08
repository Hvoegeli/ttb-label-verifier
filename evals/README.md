# Evaluation corpus

This folder answers one question a reviewer will ask: **does the rule engine actually return the right verdict?** It does so with a labeled set of "mutant" labels whose correct verdicts were decided by hand from the regulations, then checks that the code reproduces every one.

## How it works

`corpus.py` holds a single fully compliant baseline distilled-spirits label. Every case applies **one** named change to that baseline (a planted violation, or an alternate-but-valid value) and records the verdict a human says it should produce. Because only one thing changes per case, a wrong result points straight at the rule responsible.

The "ground truth" is human judgment, not model output: someone read 27 CFR Parts 5 and 16, decided PASS / FAIL / NEEDS REVIEW, and wrote it next to the mutation.

The canonical Government Warning text is **imported** from the rule module, not re-typed here, so the test fixtures can never silently drift away from what the code compares against.

## Running it

Two equivalent ways, both free (no Claude call, no API cost):

```bash
# Reviewer-facing report: per-case table + headline accuracy + JSON artifact
python -m evals.run_eval

# Same corpus as parametrized pytest cases (one named test per mutant)
pytest tests/test_eval.py -v
```

`run_eval.py` writes `results.json` (machine-readable) and exits non-zero if any verdict is wrong, so it can also gate CI.

## What this does and does not cover

- **Covers:** the deterministic rule engine end to end, every per-field rule plus the FAIL > NEEDS REVIEW > PASS aggregation and the illegible-image confidence gate. This is the half that must be 100 percent correct and reproducible.
- **Does not cover:** the vision extraction step (does Claude read the right text off a real photo). That is tested separately and manually with **real bottle photos**, because it needs a live model call and is non-deterministic by nature. Keeping the two apart is deliberate: it lets the rule logic be proven for free in CI, and isolates any extraction error from any rule error.

## Adding a case

Append an `EvalCase` to `CASES` in `corpus.py`: give it a stable `id`, the `category` it probes, a one-line `description` of the mutation, the `fields` (start from `_label(...)` and override what changes), the `expected_overall` verdict, and optionally the `expected_fields` statuses for the specific field under test.
