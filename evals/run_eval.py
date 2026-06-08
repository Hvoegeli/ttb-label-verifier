"""Standalone eval runner: prove every known verdict reproduces.

Run from the project root:

    python -m evals.run_eval

It feeds each labeled mutant through the real rule engine (no Claude call, no
cost), compares the produced verdict to the human-written ground truth, prints a
per-case table and a headline accuracy figure, and writes a JSON report to
evals/results.json for the reviewer. Exit code is 0 only if every case matches,
so this doubles as a CI gate.
"""
import json
import sys
from pathlib import Path

from app.models import ExtractedFields
from app.rules import overall_verdict, run_rules

from evals.corpus import CASES

REPORT_PATH = Path(__file__).parent / "results.json"


def evaluate_case(case):
    """Run one case through the engine and return a result record."""
    fields = ExtractedFields(**case.fields)
    outcomes = run_rules(fields)
    by_field = {o.field: o.status for o in outcomes}
    overall = overall_verdict(outcomes, fields.overall_legible)

    field_mismatches = {
        name: {"expected": want, "got": by_field.get(name)}
        for name, want in case.expected_fields.items()
        if by_field.get(name) != want
    }
    overall_ok = overall == case.expected_overall
    passed = overall_ok and not field_mismatches

    return {
        "id": case.id,
        "category": case.category,
        "description": case.description,
        "expected_overall": case.expected_overall,
        "got_overall": overall,
        "field_mismatches": field_mismatches,
        "passed": passed,
    }


def main() -> int:
    results = [evaluate_case(c) for c in CASES]
    total = len(results)
    passed = sum(1 for r in results if r["passed"])

    width = max(len(r["id"]) for r in results)
    print(f"\nTTB rule-engine eval -- {total} known-answer mutant labels\n")
    for r in results:
        mark = "ok  " if r["passed"] else "FAIL"
        line = f"  [{mark}] {r['id']:<{width}}  expected {r['expected_overall']:<12} got {r['got_overall']}"
        print(line)
        if not r["passed"]:
            for name, diff in r["field_mismatches"].items():
                print(f"          field '{name}': expected {diff['expected']}, got {diff['got']}")

    pct = (passed / total * 100) if total else 0.0
    print(f"\n{passed}/{total} verdicts reproduced ({pct:.0f}%).")
    print("Cost to run: $0.00 (rule engine only, no model call).\n")

    REPORT_PATH.write_text(
        json.dumps(
            {"total": total, "passed": passed, "accuracy_pct": round(pct, 1), "cases": results},
            indent=2,
        )
    )
    print(f"Report written to {REPORT_PATH}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
