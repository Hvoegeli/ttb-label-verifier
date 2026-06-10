"""FastAPI application and routes.

Flow (see docs/USER_FLOW.md):
    GET  /          landing: choose beverage type (primes the app on arrival)
    GET  /upload    upload form (+ optional mock application JSON)
    POST /verify    normalize image -> (extract -> rules, later) -> result page
    GET  /healthz   liveness check for the host / keep-alive

Extraction (Task Group 3) and the rule engine (Task Group 4) are not wired in
yet. Until they are, /verify validates and normalizes the image and renders the
result skeleton with a clear "pending" notice, so the app runs end to end today.
"""
import asyncio
import base64
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import costs, matcher
from .config import settings
from .extractor import ExtractionError, extract_fields
from .images import ImageValidationError, has_allowed_extension, normalize_to_jpeg
from .rules import FAIL, PASS, REVIEW, overall_verdict, run_rules

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="TTB Label Verification (Prototype)")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Beverage types. Only distilled spirits is active in the MVP; wine and beer are
# shown as "coming soon" to signal the plug-in rule architecture to reviewers.
BEVERAGES = [
    {"id": "spirits", "name": "Distilled Spirits", "active": True},
    {"id": "wine", "name": "Wine", "active": True},
    {"id": "beer", "name": "Malt Beverage / Beer", "active": True},
]
VALID_BEVERAGES = {b["id"] for b in BEVERAGES if b["active"]}


def _beverage_name(beverage: str) -> str:
    return next((b["name"] for b in BEVERAGES if b["id"] == beverage), "Alcohol")


@app.get("/healthz")
def healthz():
    """Liveness check. Also the endpoint a keep-alive pinger hits in production."""
    return {"status": "ok"}


@app.get("/stats", response_class=HTMLResponse)
def stats(request: Request, minutes_per_label: float = 7.5, hourly_rate: float = 50.0):
    """Measured efficiency report. The two assumptions (manual minutes per label and
    loaded hourly rate) are adjustable via query string so a reviewer can plug in
    their own figures; the per-label machine cost is real, from logged token usage."""
    agg = costs.aggregate()

    # Triage split: how much volume the tool cleared (PASS) vs flagged for a
    # person (FAIL + NEEDS REVIEW). Computed only over records that carry a
    # verdict, so the percentages are honest about their denominator.
    bv = agg.get("by_verdict", {})
    triage_total = sum(bv.values())
    triage = None
    if triage_total:
        cleared = bv.get("PASS", 0)
        flagged = triage_total - cleared
        triage = {
            "total": triage_total,
            "cleared": cleared,
            "flagged": flagged,
            "fail": bv.get("FAIL", 0),
            "review": bv.get("NEEDS REVIEW", 0),
            "cleared_pct": 100.0 * cleared / triage_total,
            "flagged_pct": 100.0 * flagged / triage_total,
        }

    manual_cost_per_label = (minutes_per_label / 60.0) * hourly_rate
    machine_cost_per_label = agg["avg_cost_usd"]
    savings_per_label = manual_cost_per_label - machine_cost_per_label
    ratio = (manual_cost_per_label / machine_cost_per_label) if machine_cost_per_label > 0 else None
    annual_labels = 150_000  # TTB's stated annual application volume
    context = {
        "agg": agg,
        "triage": triage,
        "minutes_per_label": minutes_per_label,
        "hourly_rate": hourly_rate,
        "manual_cost_per_label": manual_cost_per_label,
        "machine_cost_per_label": machine_cost_per_label,
        "savings_per_label": savings_per_label,
        "ratio": ratio,
        "annual_labels": annual_labels,
        "annual_manual_cost": manual_cost_per_label * annual_labels,
        "annual_machine_cost": machine_cost_per_label * annual_labels,
        "annual_savings": savings_per_label * annual_labels,
    }
    return templates.TemplateResponse(request, "stats.html", context)


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse(
        request, "landing.html", {"beverages": BEVERAGES}
    )


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request, beverage: str = "auto"):
    if beverage not in VALID_BEVERAGES and beverage != "auto":
        beverage = "auto"
    return templates.TemplateResponse(
        request, "upload.html", {"beverage": beverage, "beverage_name": _beverage_name(beverage), "error": None}
    )


async def _validate_and_normalize(image: UploadFile) -> bytes:
    """Validate one upload (type, size, decodes) and return a clean JPEG.

    Raises ImageValidationError (user-safe message) on any problem. Size is
    checked from the multipart metadata BEFORE the bytes are read into memory;
    normalize_to_jpeg adds the byte-length and pixel-dimension defenses.
    """
    if not has_allowed_extension(image.filename):
        raise ImageValidationError(
            "Unsupported file type. Please upload a JPG, PNG, WebP, or HEIC image."
        )
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if image.size is not None and image.size > max_bytes:
        raise ImageValidationError(
            f"Image is larger than the {settings.max_upload_mb} MB limit. Please upload a smaller photo."
        )
    raw = await image.read()
    return normalize_to_jpeg(raw, settings.max_upload_mb)


def _classify(selection: str, detected: str | None) -> tuple[str, str]:
    """Decide which rule set to apply AND how that decision was made.

    Returns (rule_beverage, source). `source` lets the UI describe the routing
    honestly instead of presenting every case as a confident classification:
      - "forced": the user picked a specific type; it wins over the model.
      - "detected": auto mode, and the model classified into one of the three.
      - "undetermined": auto mode, but the model returned no usable type (null or
        an out-of-enum value like "cider"); spirits is used only as a default rule
        book and the caller flags the result NEEDS REVIEW rather than trusting it.
    """
    if selection in VALID_BEVERAGES:
        return selection, "forced"
    if detected in VALID_BEVERAGES:
        return detected, "detected"
    return "spirits", "undetermined"


def _batch_type_label(pipe: dict) -> str | None:
    """How a label's type is shown in the batch table, reflecting how it was
    decided: a failed read or an undetermined type never shows a fabricated type,
    and a forced selection is marked so a coerced row is not mistaken for a read."""
    source = pipe.get("type_source")
    if source == "failed":
        return None
    if source == "undetermined":
        return "Not determined"
    name = _beverage_name(pipe["beverage"])
    return f"{name} (forced)" if source == "forced" else name


def _run_pipeline(jpegs: list[bytes], selection: str = "auto") -> dict:
    """Shared per-label core: one vision call -> rules -> verdict, cost recorded.

    The vision read is universal: it classifies the beverage type and reads every
    beverage's fields. `selection` is the user's choice: a specific type forces
    that rule set (an override), while 'auto' routes by the detected type. This is
    what lets a mixed pile of labels each get judged by the right rule book.

    Both /verify (one label) and /batch (many) call this so every verdict comes
    from the same audited path. Returns a plain dict; callers shape it for their
    own page. Never raises: an extraction failure or an illegible image comes
    back as a NEEDS REVIEW result with a human-readable note, because in a batch
    one bad photo must not abort the rest.
    """
    started = time.perf_counter()
    try:
        extraction = extract_fields(jpegs)
    except ExtractionError as exc:
        # Nothing was read, so no type was determined. Use a default rule book
        # name internally but mark the source "failed" so the UI does not claim
        # the label was classified.
        return {
            "overall": "NEEDS REVIEW",
            "outcomes": [],
            "fields": None,
            "extraction": None,
            "beverage": _classify(selection, None)[0],
            "detected": None,
            "type_source": "failed",
            "overridden": False,
            "note": str(exc),
            "processing_ms": (time.perf_counter() - started) * 1000,
            "cost_usd": None,
        }

    processing_ms = (time.perf_counter() - started) * 1000
    fields = extraction.fields
    detected = fields.beverage_type
    beverage, type_source = _classify(selection, detected)
    # True when the user forced a type that disagrees with what the label looks like.
    overridden = type_source == "forced" and detected in VALID_BEVERAGES and detected != selection

    # Confidence gate: never run compliance checks on an image we could not read.
    if not fields.overall_legible:
        outcomes = []
        overall = "NEEDS REVIEW"
        note = "The image was not clear enough to read confidently. Please upload a sharper, well-lit, straight-on photo."
    else:
        outcomes = run_rules(fields, beverage)
        overall = overall_verdict(outcomes, fields.overall_legible)
        note = None
        # Auto mode but the model could not classify the beverage: we ran spirits
        # rules only as a default, so do not trust the verdict; route to a human.
        if type_source == "undetermined":
            overall = "NEEDS REVIEW"
            note = ("The beverage type could not be determined from the label, so it was "
                    "checked under distilled-spirits rules as a default. Confirm the type "
                    "and re-check by hand.")

    # Record the measured cost + latency + verdict for the efficiency report
    # (/stats). Done after the verdict so the triage split can be logged.
    costs.record(
        model=extraction.model or settings.claude_model,
        input_tokens=extraction.input_tokens,
        output_tokens=extraction.output_tokens,
        cost_usd=extraction.cost_usd,
        latency_ms=processing_ms,
        verdict=overall,
    )

    return {
        "overall": overall,
        "outcomes": outcomes,
        "fields": fields,
        "extraction": extraction,
        "escalated": extraction.escalated,
        "beverage": beverage,
        "detected": detected,
        "type_source": type_source,
        "overridden": overridden,
        "note": note,
        "processing_ms": processing_ms,
        "cost_usd": extraction.cost_usd,
    }


@app.post("/verify", response_class=HTMLResponse)
async def verify(
    request: Request,
    image: UploadFile = File(...),
    image_back: UploadFile | None = File(default=None),
    beverage: str = Form(default="auto"),
    app_brand_name: str = Form(default=""),
    app_fanciful_name: str = Form(default=""),
    app_class_type: str = Form(default=""),
    app_alcohol_content: str = Form(default=""),
    app_net_contents: str = Form(default=""),
    app_appellation: str = Form(default=""),
    app_grape_varietal: str = Form(default=""),
    app_vintage: str = Form(default=""),
    app_serial_number: str = Form(default=""),
    app_source_of_product: str = Form(default=""),
    app_formula_number: str = Form(default=""),
    app_permit_no: str = Form(default=""),
):
    # Validate and normalize the front label (required) and the back label
    # (optional). Real bottles split mandatory fields across both faces, so both
    # photos go to the model in one call.
    try:
        jpegs = [await _validate_and_normalize(image)]
        if image_back is not None and image_back.filename:
            jpegs.append(await _validate_and_normalize(image_back))
    except ImageValidationError as exc:
        return templates.TemplateResponse(
            request,
            "upload.html",
            {"beverage": beverage, "beverage_name": _beverage_name(beverage), "error": str(exc)},
            status_code=400,
        )

    # Show the cleaned image(s) back to the user as previews.
    previews = [base64.b64encode(j).decode("ascii") for j in jpegs]

    # Guard the selection: anything outside the three rule sets means auto-detect.
    if beverage not in VALID_BEVERAGES:
        beverage = "auto"

    # One vision call reads the fields across all supplied images and detects the
    # beverage type; the rule engine then judges them under the detected type unless
    # the user forced one. Shared with /batch so both compute verdicts identically.
    pipe = _run_pipeline(jpegs, beverage)
    fields = pipe["fields"]
    outcomes = pipe["outcomes"]
    overall = pipe["overall"]
    note = pipe["note"]
    processing_ms = pipe["processing_ms"]
    resolved = pipe["beverage"]
    detected = pipe["detected"]
    overridden = pipe["overridden"]
    type_source = pipe["type_source"]

    # Extraction failed outright: nothing was read, so route to human review with
    # the safe message and skip the (impossible) field display and comparisons.
    if fields is None:
        result = {
            "overall": overall,
            "fields": [],
            "extracted": None,
            "match": None,
            "note": note,
            "processing_ms": processing_ms,
            "cost_usd": pipe["cost_usd"],
        }
        return templates.TemplateResponse(
            request, "result.html",
            {"result": result, "previews": previews, "beverage": beverage,
             "detected_beverage": detected, "resolved_beverage": resolved,
             "type_source": type_source, "overridden": overridden,
             "beverage_name": _beverage_name(resolved)},
        )

    # Advisory (Tier 2) notes: format/size/placement checks a photo cannot prove.
    # Surfaced for a human, never a pass/fail gate. Pulled from rule detail.
    advisories = [
        {"field": o.field, "text": o.detail["tier2_advisory"], "citation": o.citation}
        for o in outcomes
        if o.detail and o.detail.get("tier2_advisory")
    ]

    # When the warning does not match, surface what the statute expects vs what
    # was read off the label, so a human can tell a real defect from a photo
    # mis-transcription (the most common failure on a curved back label).
    warning_diff = None
    for o in outcomes:
        if o.field == "Government warning" and o.status != "PASS" and o.detail:
            expected = o.detail.get("expected_near") or o.detail.get("expected")
            got = o.detail.get("got_near") or o.detail.get("got")
            if expected or got:
                warning_diff = {"expected": expected, "got": got}
        if o.field == "Government warning":
            break

    # Optional match check: compare the label against the application (TTB Form
    # 5100.31 fields entered in the upload panel). Only the matchable fields, those
    # the label and the filing have in common, go to the matcher.
    app_data = {
        "brand_name": app_brand_name,
        "fanciful_name": app_fanciful_name,
        "class_type": app_class_type,
        "alcohol_content": app_alcohol_content,
        "net_contents": app_net_contents,
        "appellation": app_appellation,
        "grape_varietal": app_grape_varietal,
        "vintage": app_vintage,
    }
    app_data = {k: v.strip() for k, v in app_data.items() if v and v.strip()}
    # Appellation, grape varietal, and vintage only apply to wine. If the label was
    # not judged as wine (the auto-mode panel still offers them), drop them so they
    # do not produce a confusing "not found" row against a spirits/beer label.
    if resolved != "wine":
        for k in ("appellation", "grape_varietal", "vintage"):
            app_data.pop(k, None)
    match_rows = [m.as_row() for m in matcher.compare(fields, app_data)] or None if app_data else None
    match_error = None

    # Filing details that have no counterpart on the label: shown for reference,
    # never matched. These mirror the application-only items of Form 5100.31.
    filing_context = [
        {"field": label, "value": value.strip()}
        for label, value in [
            ("Serial number", app_serial_number),
            ("Source of product", app_source_of_product),
            ("Formula number", app_formula_number),
            ("Plant registry / permit no.", app_permit_no),
        ]
        if value and value.strip()
    ] or None

    # Only the content fields are displayed; the legibility flags drive logic, not the table.
    extracted = {
        "Brand name": fields.brand_name,
        "Class/type": fields.class_type,
        "Alcohol content": fields.alcohol_content,
        "Net contents": fields.net_contents,
        "Name and address": fields.name_and_address,
        "Government warning": fields.government_warning,
    }
    # Country of origin is shown only when read, since it is relevant to imports.
    if fields.country_of_origin:
        extracted["Country of origin"] = fields.country_of_origin
    if resolved == "wine":
        extracted["Appellation"] = fields.appellation
        extracted["Vintage"] = fields.vintage
        extracted["Grape varietal"] = fields.grape_varietal
        extracted["Sulfite statement"] = fields.sulfite_statement
    elif resolved == "beer" and fields.statement_of_composition:
        extracted["Statement of composition"] = fields.statement_of_composition

    # A quick tally of the mandatory (Golden Rule) checks for the result header,
    # so a reviewer sees "4 of 5 mandatory checks passed" at a glance.
    golden = [o for o in outcomes if getattr(o, "golden", True)]
    tally = {
        "total": len(golden),
        "pass": sum(1 for o in golden if o.status == PASS),
        "fail": sum(1 for o in golden if o.status == FAIL),
        "review": sum(1 for o in golden if o.status == REVIEW),
    }

    result = {
        "overall": overall,
        "fields": [o.as_row() for o in outcomes],
        "extracted": extracted,
        "match": match_rows,
        "match_error": match_error,
        "filing_context": filing_context,
        "advisories": advisories or None,
        "warning_diff": warning_diff,
        "note": note,
        "tally": tally,
        "escalated": pipe.get("escalated", False),
        "processing_ms": processing_ms,
        "cost_usd": pipe["cost_usd"],
    }
    return templates.TemplateResponse(
        request,
        "result.html",
        {"result": result, "previews": previews, "beverage": beverage,
         "detected_beverage": detected, "resolved_beverage": resolved,
         "type_source": type_source, "overridden": overridden,
         "beverage_name": _beverage_name(resolved)},
    )


# Volumes the batch result page projects the measured per-label figures out to:
# the presearch headline batch and TTB's stated annual application volume.
_PROJECTION_VOLUMES = [300, 150_000]


def _summarize_outcomes(outcomes: list) -> str:
    """One-line reason for the batch table: the mandatory checks that did not pass."""
    problems = [
        f"{o.field}: {o.reason}"
        for o in outcomes
        if o.status != "PASS" and getattr(o, "golden", True)
    ]
    return "; ".join(problems)


@app.get("/batch", response_class=HTMLResponse)
def batch_page(request: Request, beverage: str = "auto"):
    if beverage not in VALID_BEVERAGES and beverage != "auto":
        beverage = "auto"
    return templates.TemplateResponse(
        request,
        "batch_upload.html",
        {
            "beverage": beverage,
            "beverage_name": _beverage_name(beverage),
            "max_batch": settings.max_batch,
            "error": None,
        },
    )


@app.post("/batch", response_class=HTMLResponse)
async def batch_verify(
    request: Request,
    images: list[UploadFile] = File(default=[]),
    beverage: str = Form(default="auto"),
):
    """Verify many labels in one request (one image per label, front face).

    Each label runs the same shared pipeline as the single-label path, concurrently.
    By default the beverage type is auto-detected per label, so a mixed pile (some
    wine, some beer, some spirits) is each judged by the right rule set; a specific
    selection forces one rule set for every label. One unreadable photo becomes a
    NEEDS REVIEW row rather than aborting the run. A demo-sized cap keeps the request
    responsive; the result page projects the real per-label cost and time to volume.
    """
    if beverage not in VALID_BEVERAGES and beverage != "auto":
        beverage = "auto"

    # Ignore empty file parts the browser may submit for an untouched input.
    files = [f for f in images if f is not None and f.filename]

    def _reject(message: str):
        return templates.TemplateResponse(
            request,
            "batch_upload.html",
            {
                "beverage": beverage,
                "beverage_name": _beverage_name(beverage),
                "max_batch": settings.max_batch,
                "error": message,
            },
            status_code=400,
        )

    if not files:
        return _reject("Please choose at least one label image to verify.")
    if len(files) > settings.max_batch:
        return _reject(
            f"This demo verifies up to {settings.max_batch} labels at once "
            f"(you selected {len(files)}). For production volumes of 200 to 300, "
            "the labels would run on a background queue; see the note on the batch page."
        )

    # Normalize all images first (fast, local CPU work). Defer the slow per-label
    # model calls so they can run concurrently below. An unreadable file is held as
    # an error and becomes a NEEDS REVIEW row, never aborting the run.
    prepared = []
    for f in files:
        try:
            jpeg = await _validate_and_normalize(f)
            prepared.append({"filename": f.filename, "jpeg": jpeg, "error": None})
        except ImageValidationError as exc:
            prepared.append({"filename": f.filename, "jpeg": None, "error": str(exc)})

    # Read the labels concurrently. Each label is one network-bound model call, so
    # overlapping them cuts batch wall-clock by roughly BATCH_CONCURRENCY-fold. The
    # per-label cost and latency recorded inside _run_pipeline are per-label and
    # unchanged, so the measured efficiency figures stay honest; only the total
    # wall-clock shrinks. gather preserves order, so rows still map to filenames.
    loop = asyncio.get_running_loop()
    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=settings.batch_concurrency) as pool:
        async def _process(item):
            if item["jpeg"] is None:
                return None
            return await loop.run_in_executor(pool, _run_pipeline, [item["jpeg"]], beverage)
        pipes = await asyncio.gather(*(_process(item) for item in prepared))
    wall_clock_seconds = time.perf_counter() - wall_start

    rows = []
    for item, pipe in zip(prepared, pipes):
        if item["error"] is not None:
            rows.append({
                "filename": item["filename"],
                "type": None,
                "overall": "NEEDS REVIEW",
                "reason": item["error"],
                "cost_usd": None,
                "processing_ms": 0.0,
            })
            continue
        reason = pipe["note"] or _summarize_outcomes(pipe["outcomes"]) or "All mandatory checks passed."
        rows.append({
            "filename": item["filename"],
            # The type the label was judged as, marked forced/undetermined/failed so
            # a mixed batch makes its routing visible without fabricating a type.
            "type": _batch_type_label(pipe),
            "overall": pipe["overall"],
            "reason": reason,
            "cost_usd": pipe["cost_usd"],
            "processing_ms": pipe["processing_ms"],
        })

    count = len(rows)
    counts = {"PASS": 0, "FAIL": 0, "NEEDS REVIEW": 0}
    for r in rows:
        counts[r["overall"]] = counts.get(r["overall"], 0) + 1
    total_cost = sum(r["cost_usd"] or 0.0 for r in rows)
    total_ms = sum(r["processing_ms"] for r in rows)
    avg_cost = total_cost / count if count else 0.0
    avg_seconds = (total_ms / count / 1000) if count else 0.0

    # Honest extrapolation: multiply the measured per-label figures by larger
    # volumes. Time assumes the same serial rate (a real queue would parallelize,
    # so this is a conservative upper bound on wall-clock).
    projections = [
        {
            "volume": v,
            "cost": avg_cost * v,
            "hours": (avg_seconds * v) / 3600,
        }
        for v in _PROJECTION_VOLUMES
    ]

    summary = {
        "count": count,
        "counts": counts,
        "total_cost": total_cost,
        "total_seconds": total_ms / 1000,
        "avg_cost": avg_cost,
        "avg_seconds": avg_seconds,
        # Actual elapsed time for the whole batch. Because labels run concurrently,
        # this is much less than total_seconds (the one-at-a-time equivalent).
        "wall_clock_seconds": wall_clock_seconds,
        "projections": projections,
    }
    return templates.TemplateResponse(
        request,
        "batch_result.html",
        {"rows": rows, "summary": summary, "beverage": beverage, "beverage_name": _beverage_name(beverage)},
    )
