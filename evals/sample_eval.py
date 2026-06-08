"""Live full-pipeline eval on the synthetic sample labels.

The free test (tests/test_sample_labels.py) already proved the manifest's expected
verdicts are correct per the rules. This eval closes the loop: it runs each
rendered IMAGE through the real pipeline (vision read -> rule engine) and checks
the verdict matches the expected one. It therefore measures the one thing the
free test cannot, the vision read, but on labels we control (clean printed text),
so a mismatch points at the model's extraction rather than an unknown ground truth.

It calls the live model, so it costs a few cents and is non-deterministic. Run
locally with a key in .env:

    python -m evals.sample_eval

A summary is written to evals/sample_results.md (gitignored: it changes per run
and per model).
"""
import json
import time
from pathlib import Path

from app.config import settings
from app.extractor import ExtractionError, extract_fields
from app.images import normalize_to_jpeg
from app.rules import overall_verdict, run_rules

MANIFEST = Path(__file__).resolve().parent.parent / "sample_labels" / "manifest.json"
REPORT_PATH = Path(__file__).parent / "sample_results.md"


def evaluate(entry: dict) -> dict:
    """Run one rendered label image through the live pipeline and grade it."""
    image_path = MANIFEST.parent / entry["file"]
    jpeg = normalize_to_jpeg(image_path.read_bytes(), settings.max_upload_mb)

    started = time.perf_counter()
    extraction = extract_fields(jpeg, entry["beverage"])
    latency_ms = (time.perf_counter() - started) * 1000

    fields = extraction.fields
    if not fields.overall_legible:
        outcomes = []
        overall = "NEEDS REVIEW"
    else:
        outcomes = run_rules(fields, entry["beverage"])
        overall = overall_verdict(outcomes, fields.overall_legible)

    expected = entry["expected"]
    match = overall == expected
    return {
        "entry": entry,
        "fields": fields,
        "outcomes": outcomes,
        "overall": overall,
        "expected": expected,
        "match": match,
        "cost_usd": extraction.cost_usd,
        "latency_ms": latency_ms,
    }


def main() -> int:
    if not settings.anthropic_api_key:
        print("No ANTHROPIC_API_KEY set. This eval calls the live model; set the key in .env first.")
        return 2
    if not MANIFEST.exists():
        print(f"No manifest at {MANIFEST}. Run `python -m sample_labels.generate` first.")
        return 2

    entries = json.loads(MANIFEST.read_text())
    results = []
    for entry in entries:
        try:
            results.append(evaluate(entry))
        except ExtractionError as exc:
            print(f"  [skip] {entry['id']}: {exc}")

    if not results:
        print("No labels evaluated.")
        return 1

    matched = sum(1 for r in results if r["match"])
    total_cost = sum(r["cost_usd"] for r in results)
    accuracy = matched / len(results) * 100

    print(f"\nSample-label live eval -- {len(results)} labels, model {settings.claude_model}")
    print(f"Full-pipeline accuracy: {matched}/{len(results)} ({accuracy:.0f}%)\n")
    for r in results:
        flag = "ok " if r["match"] else "X  "
        print(f"  {flag}{r['entry']['id']}: got {r['overall']}, expected {r['expected']}  "
              f"${r['cost_usd']:.4f}  {r['latency_ms']:.0f}ms")

    lines = ["# Sample-label live eval results\n"]
    lines.append(
        "Full-pipeline run (vision read -> rule engine) on the synthetic sample "
        "labels, whose expected verdicts are independently proven by "
        "tests/test_sample_labels.py. A mismatch here points at the model's read "
        "of a clean printed label, not at unknown ground truth. Live model, so "
        "non-deterministic and not free.\n"
    )
    lines.append(f"- Model: `{settings.claude_model}`")
    lines.append(f"- Labels: {len(results)}")
    lines.append(f"- Full-pipeline accuracy: {matched}/{len(results)} ({accuracy:.0f}%)")
    lines.append(f"- Total cost: ${total_cost:.4f}")
    lines.append(f"- Average latency: {sum(r['latency_ms'] for r in results)/len(results):.0f} ms\n")

    lines.append("| Label | Beverage | Expected | Got | Result |")
    lines.append("| --- | --- | --- | --- | --- |")
    for r in results:
        lines.append(f"| {r['entry']['id']} | {r['entry']['beverage']} | {r['expected']} | "
                     f"{r['overall']} | {'match' if r['match'] else 'MISMATCH'} |")
    lines.append("")

    mismatches = [r for r in results if not r["match"]]
    if mismatches:
        lines.append("## Mismatches to read\n")
        for r in mismatches:
            lines.append(f"### {r['entry']['id']} (expected {r['expected']}, got {r['overall']})\n")
            lines.append(f"- Planted: {r['entry']['planted']}")
            lines.append(f"- Warning read: {(r['fields'].government_warning or '(none)')[:120]}")
            if r["outcomes"]:
                for o in r["outcomes"]:
                    lines.append(f"  - {o.field}: {o.status} ({o.citation}) {o.reason}")
            lines.append("")
    else:
        lines.append("All labels reproduced their expected verdict through the full pipeline.\n")

    REPORT_PATH.write_text("\n".join(lines))
    print(f"\nTotal cost: ${total_cost:.4f}. Report written to {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
