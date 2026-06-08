"""Manual extraction eval on real bottle photos (front + back pairs).

Unlike the deterministic golden set, this calls the live model, so it costs a few
cents and is non-deterministic. It tests the half the golden set cannot: can the
model read real, curved, glare-prone labels well enough that the rule engine
reaches the right verdict, and does the front+back pairing supply the fields that
are split across faces?

Run locally with a key set in .env:

    python -m evals.real_eval

Photos live in evals/real_photos/ (gitignored, local only). A summary is written
to evals/real_results.md (committed, no images).

Ground truth: all three bottles were bought legally in the US, so the lawful
verdict is "compliant", which means the tool should NOT return FAIL. A PASS is
the ideal result; a NEEDS REVIEW is acceptable (the tool erring toward a human
rather than guessing) but is flagged as a coverage note; a FAIL on a compliant
bottle is a real concern to investigate.
"""
import time
from pathlib import Path

from app.config import settings
from app.extractor import ExtractionError, extract_fields
from app.images import ImageValidationError, normalize_to_jpeg
from app.rules import FAIL, PASS, REVIEW, overall_verdict, run_rules

PHOTO_DIR = Path(__file__).parent / "real_photos"
REPORT_PATH = Path(__file__).parent / "real_results.md"

BOTTLES = [
    {"id": "tequila", "name": "Tequila", "scope": "spirits"},
    {"id": "gin", "name": "Gin", "scope": "spirits"},
    {"id": "baileys", "name": "Baileys Irish Cream", "scope": "spirits"},
    # Out-of-distribution boundary tests. The MVP is distilled spirits only.
    # Sake is a fermented rice product regulated as wine (27 CFR Part 4); soju is
    # distilled but unusual and not in our recognized spirits set. The correct
    # behavior for these is NEEDS REVIEW (route to a human), not a confident
    # verdict; a fill or class FAIL here is a scope artifact, not a label defect.
    {"id": "soju", "name": "Soju (out of scope: edge spirit)", "scope": "edge"},
    {"id": "sake", "name": "Sake (out of scope: wine, Part 4)", "scope": "wine"},
]

FIELDS_SHOWN = [
    ("brand_name", "Brand"),
    ("class_type", "Class/type"),
    ("alcohol_content", "Alcohol"),
    ("net_contents", "Net contents"),
    ("name_and_address", "Name/address"),
]


def _load_pair(bottle_id: str) -> list[bytes]:
    """Normalize the front and back HEIC photos for one bottle into JPEGs."""
    jpegs = []
    for face in ("front", "back"):
        path = PHOTO_DIR / f"{bottle_id}_{face}.heic"
        if not path.exists():
            raise FileNotFoundError(f"Missing photo: {path}")
        jpegs.append(normalize_to_jpeg(path.read_bytes(), settings.max_upload_mb))
    return jpegs


def evaluate(bottle: dict) -> dict:
    """Run one bottle (front+back) through the live pipeline and grade it."""
    jpegs = _load_pair(bottle["id"])
    started = time.perf_counter()
    extraction = extract_fields(jpegs)
    latency_ms = (time.perf_counter() - started) * 1000

    fields = extraction.fields
    if not fields.overall_legible:
        outcomes = []
        overall = REVIEW
    else:
        outcomes = run_rules(fields)
        overall = overall_verdict(outcomes, fields.overall_legible)

    # Grade against ground truth. In-scope spirits should not FAIL (compliant).
    # Out-of-scope beverages (sake=wine, soju=edge) SHOULD route to review rather
    # than be confidently judged by spirits rules; a FAIL there is a scope artifact.
    scope = bottle.get("scope", "spirits")
    if scope != "spirits":
        if overall == REVIEW:
            grade = "ideal for out-of-scope (routed to human review)"
        elif overall == FAIL:
            grade = "scope artifact (out-of-scope beverage judged by spirits rules)"
        else:
            grade = "passed under spirits rules (note: outside MVP scope)"
    elif overall == FAIL:
        grade = "CONCERN (compliant bottle returned FAIL)"
    elif overall == REVIEW:
        grade = "acceptable (routed to human review)"
    else:
        grade = "ideal (PASS)"

    return {
        "bottle": bottle,
        "fields": fields,
        "outcomes": outcomes,
        "overall": overall,
        "grade": grade,
        "cost_usd": extraction.cost_usd,
        "latency_ms": latency_ms,
        "input_tokens": extraction.input_tokens,
        "output_tokens": extraction.output_tokens,
    }


def _warning_preview(text: str | None) -> str:
    if not text:
        return "(none read)"
    text = " ".join(text.split())
    return text if len(text) <= 90 else text[:87] + "..."


def main() -> int:
    if not settings.anthropic_api_key:
        print("No ANTHROPIC_API_KEY set. This eval calls the live model; set the key in .env first.")
        return 2
    if not PHOTO_DIR.exists():
        print(f"No photos found at {PHOTO_DIR}. Drop the front/back HEIC pairs there first.")
        return 2

    results = []
    for bottle in BOTTLES:
        try:
            results.append(evaluate(bottle))
        except (FileNotFoundError, ImageValidationError, ExtractionError) as exc:
            print(f"  [skip] {bottle['name']}: {exc}")

    if not results:
        print("No bottles evaluated.")
        return 1

    total_cost = sum(r["cost_usd"] for r in results)
    lines = []
    lines.append("# Real-photo extraction eval results\n")
    lines.append(
        "Live-model extraction on real bottle photos (front + back pairs), one Claude "
        "call per bottle across both faces. Non-deterministic and not free, so this is a "
        "manual run, separate from the deterministic golden set. Photos are local only "
        "(gitignored). Ground truth: all bottles were bought legally in the US, so the "
        "lawful verdict is compliant (should not FAIL).\n"
    )
    lines.append(f"- Model: `{settings.claude_model}`")
    lines.append(f"- Bottles: {len(results)}")
    lines.append(f"- Total cost: ${total_cost:.4f}")
    lines.append(f"- Average latency: {sum(r['latency_ms'] for r in results)/len(results):.0f} ms\n")

    print(f"\nReal-photo extraction eval -- {len(results)} bottles, model {settings.claude_model}\n")
    for r in results:
        b = r["bottle"]
        print(f"  {b['name']}: {r['overall']}  [{r['grade']}]  ${r['cost_usd']:.4f}  {r['latency_ms']:.0f}ms")

        lines.append(f"## {b['name']}\n")
        lines.append(f"- Verdict: **{r['overall']}** ({r['grade']})")
        lines.append(f"- Cost: ${r['cost_usd']:.4f} | Latency: {r['latency_ms']:.0f} ms | "
                     f"Tokens: {r['input_tokens']} in / {r['output_tokens']} out")
        lines.append("- Fields read:")
        for attr, label in FIELDS_SHOWN:
            lines.append(f"  - {label}: {getattr(r['fields'], attr)!r}")
        lines.append(f"  - Government warning: {_warning_preview(r['fields'].government_warning)}")
        lines.append(f"  - Legibility: warning={r['fields'].warning_legible}, overall={r['fields'].overall_legible}")
        if r["outcomes"]:
            lines.append("- Per-rule outcomes:")
            for o in r["outcomes"]:
                lines.append(f"  - {o.field}: {o.status} ({o.citation}) {o.reason}")
        lines.append("")

    lines.append("## Reading\n")
    lines.append(
        "A PASS confirms the model read real-world labels well enough for the rule engine "
        "to clear a compliant bottle. A NEEDS REVIEW usually means either a legibility flag "
        "(glare or curvature on the photo) or a class/type term outside the recognized set, "
        "both of which correctly route to a human rather than guessing. A FAIL on a bottle "
        "we know is compliant is the signal to investigate (often the warning not being read "
        "verbatim off a curved back label).\n"
    )

    REPORT_PATH.write_text("\n".join(lines))
    print(f"\nTotal cost: ${total_cost:.4f}. Report written to {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
