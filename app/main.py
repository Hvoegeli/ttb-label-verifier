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
import base64
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import settings
from .extractor import ExtractionError, extract_fields
from .images import ImageValidationError, has_allowed_extension, normalize_to_jpeg

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="TTB Label Verification (Prototype)")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Beverage types. Only distilled spirits is active in the MVP; wine and beer are
# shown as "coming soon" to signal the plug-in rule architecture to reviewers.
BEVERAGES = [
    {"id": "spirits", "name": "Distilled Spirits", "active": True},
    {"id": "wine", "name": "Wine", "active": False},
    {"id": "beer", "name": "Malt Beverage / Beer", "active": False},
]


@app.get("/healthz")
def healthz():
    """Liveness check. Also the endpoint a keep-alive pinger hits in production."""
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse(
        request, "landing.html", {"beverages": BEVERAGES}
    )


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request, beverage: str = "spirits"):
    return templates.TemplateResponse(
        request, "upload.html", {"beverage": beverage, "error": None}
    )


@app.post("/verify", response_class=HTMLResponse)
async def verify(
    request: Request,
    image: UploadFile = File(...),
    application: str = Form(default=""),
    beverage: str = Form(default="spirits"),
):
    # Friendly early rejection on obviously wrong file types.
    if not has_allowed_extension(image.filename):
        return templates.TemplateResponse(
            request,
            "upload.html",
            {
                "beverage": beverage,
                "error": "Unsupported file type. Please upload a JPG, PNG, WebP, or HEIC image.",
            },
            status_code=400,
        )

    # Reject an oversized upload using the size the multipart parser already
    # knows, BEFORE reading the bytes into this process. normalize_to_jpeg keeps
    # its own byte-length check as defense in depth.
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if image.size is not None and image.size > max_bytes:
        return templates.TemplateResponse(
            request,
            "upload.html",
            {
                "beverage": beverage,
                "error": f"Image is larger than the {settings.max_upload_mb} MB limit. Please upload a smaller photo.",
            },
            status_code=400,
        )

    raw = await image.read()
    try:
        jpeg = normalize_to_jpeg(raw, settings.max_upload_mb)
    except ImageValidationError as exc:
        return templates.TemplateResponse(
            request,
            "upload.html",
            {"beverage": beverage, "error": str(exc)},
            status_code=400,
        )

    # Show the cleaned image back to the user as a preview.
    image_b64 = base64.b64encode(jpeg).decode("ascii")

    # One vision call extracts the fields. Time it so we can show (and prove) the
    # per-label latency. Rule checks (Task Group 4) are not wired in yet.
    started = time.perf_counter()
    try:
        fields = extract_fields(jpeg)
    except ExtractionError as exc:
        result = {
            "overall": "NEEDS REVIEW",
            "fields": [],
            "extracted": None,
            "match": None,
            "note": f"{exc}",
            "processing_ms": (time.perf_counter() - started) * 1000,
        }
        return templates.TemplateResponse(
            request, "result.html",
            {"result": result, "image_b64": image_b64, "beverage": beverage},
        )

    processing_ms = (time.perf_counter() - started) * 1000

    # Confidence gate: never auto-pass an image we could not read confidently.
    if not fields.overall_legible:
        overall = "NEEDS REVIEW"
        note = "The image was not clear enough to read confidently. Please upload a sharper, well-lit, straight-on photo."
    else:
        overall = "PENDING"
        note = "Fields read from the label. Compliance rule checks are added in the next task group."

    # Only the content fields are displayed; the legibility flags drive logic, not the table.
    extracted = {
        "Brand name": fields.brand_name,
        "Class/type": fields.class_type,
        "Alcohol content": fields.alcohol_content,
        "Net contents": fields.net_contents,
        "Name and address": fields.name_and_address,
        "Government warning": fields.government_warning,
    }

    result = {
        "overall": overall,
        "fields": [],            # rule rows arrive in Task Group 4
        "extracted": extracted,
        "match": None,
        "note": note,
        "processing_ms": processing_ms,
    }
    return templates.TemplateResponse(
        request,
        "result.html",
        {"result": result, "image_b64": image_b64, "beverage": beverage},
    )
