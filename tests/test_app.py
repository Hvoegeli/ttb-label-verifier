"""Smoke tests for the app shell (Task Groups 1 and 2).

These exercise the routes and the image normalization. They do not call the
Claude model (that arrives in Task Group 3 and will be mocked in CI).
"""
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main as main_module
from app import costs as costs_module
from app.extractor import ExtractedFields, ExtractionError, ExtractionResult
from app.main import app
from app.rules.warning import CANONICAL as WARNING_TEXT

client = TestClient(app)


@pytest.fixture(autouse=True)
def _tmp_metrics(tmp_path, monkeypatch):
    """Redirect the metrics log to a temp file so tests never write into the repo."""
    monkeypatch.setattr(costs_module, "METRICS_PATH", tmp_path / "usage.jsonl")


def _fake_fields(**overrides):
    """A clean, compliant-looking extraction for tests (model never really runs)."""
    base = dict(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        name_and_address="Old Tom Distillery, Bardstown, KY",
        government_warning=WARNING_TEXT,
        warning_legible=True,
        overall_legible=True,
    )
    base.update(overrides)
    return ExtractedFields(**base)


def _fake_result(**overrides):
    """Wrap fake fields in an ExtractionResult with fixed token usage/cost."""
    return ExtractionResult(
        fields=_fake_fields(**overrides),
        input_tokens=2100,
        output_tokens=400,
        cost_usd=0.0042,
    )


def _png_bytes(size=(60, 40), color=(200, 120, 40)):
    """A tiny valid PNG to use as a fake upload."""
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_landing_lists_spirits():
    r = client.get("/")
    assert r.status_code == 200
    assert "Distilled Spirits" in r.text


def test_upload_page_renders():
    r = client.get("/upload")
    assert r.status_code == 200
    assert "Upload a distilled spirits label" in r.text


def test_verify_extracts_and_shows_fields(monkeypatch):
    # Mock the vision call so the test is free and deterministic.
    monkeypatch.setattr(main_module, "extract_fields", lambda jpeg: _fake_result())
    files = {"image": ("label.png", _png_bytes(), "image/png")}
    r = client.post("/verify", files=files, data={"beverage": "spirits"})
    assert r.status_code == 200
    assert "OLD TOM DISTILLERY" in r.text  # extracted field shown
    assert "PASS" in r.text                # fully compliant fixture -> overall PASS
    assert "27 CFR" in r.text              # CFR citations rendered
    assert "0.0042" in r.text              # per-label cost shown


def test_verify_illegible_routes_to_review(monkeypatch):
    monkeypatch.setattr(
        main_module, "extract_fields", lambda jpeg: _fake_result(overall_legible=False)
    )
    files = {"image": ("label.png", _png_bytes(), "image/png")}
    r = client.post("/verify", files=files, data={"beverage": "spirits"})
    assert r.status_code == 200
    assert "NEEDS REVIEW" in r.text


def test_verify_extraction_error_routes_to_review(monkeypatch):
    def boom(jpeg):
        raise ExtractionError("The label-reading service was unavailable. Please try again.")

    monkeypatch.setattr(main_module, "extract_fields", boom)
    files = {"image": ("label.png", _png_bytes(), "image/png")}
    r = client.post("/verify", files=files, data={"beverage": "spirits"})
    assert r.status_code == 200
    assert "NEEDS REVIEW" in r.text
    assert "unavailable" in r.text


def test_verify_rejects_non_image_extension():
    files = {"image": ("notes.txt", b"hello", "text/plain")}
    r = client.post("/verify", files=files, data={"beverage": "spirits"})
    assert r.status_code == 400
    assert "Unsupported file type" in r.text


def test_verify_rejects_oversized_before_read(monkeypatch):
    # Set the limit to 0 MB so any non-empty upload is "too large", and confirm
    # the early size gate (based on UploadFile.size) rejects it.
    import app.main as m

    monkeypatch.setattr(m.settings, "max_upload_mb", 0)
    files = {"image": ("label.png", _png_bytes(), "image/png")}
    r = client.post("/verify", files=files, data={"beverage": "spirits"})
    assert r.status_code == 400
    assert "larger than the 0 MB limit" in r.text


def test_verify_rejects_corrupt_image():
    # Right extension, but the bytes are not a real image.
    files = {"image": ("fake.png", b"this is not a png", "image/png")}
    r = client.post("/verify", files=files, data={"beverage": "spirits"})
    assert r.status_code == 400
    assert "Could not read this file" in r.text


def test_cost_usd_matches_published_pricing():
    # 1M input + 1M output on Haiku = $1.00 + $5.00 = $6.00
    assert abs(costs_module.cost_usd("claude-haiku-4-5", 1_000_000, 1_000_000) - 6.00) < 1e-9
    # Sonnet = $3.00 + $15.00 = $18.00
    assert abs(costs_module.cost_usd("claude-sonnet-4-6", 1_000_000, 1_000_000) - 18.00) < 1e-9
    # Unknown model contributes no cost rather than crashing.
    assert costs_module.cost_usd("nope", 1000, 1000) == 0.0


def test_stats_empty_before_any_verification():
    r = client.get("/stats")
    assert r.status_code == 200
    assert "No labels have been verified yet" in r.text


def test_stats_records_and_aggregates(monkeypatch):
    monkeypatch.setattr(main_module, "extract_fields", lambda jpeg: _fake_result())
    files = {"image": ("label.png", _png_bytes(), "image/png")}
    client.post("/verify", files=files, data={"beverage": "spirits"})

    agg = costs_module.aggregate()
    assert agg["count"] == 1
    assert abs(agg["total_cost_usd"] - 0.0042) < 1e-9

    r = client.get("/stats")
    assert r.status_code == 200
    assert "labels verified" in r.text
    assert "cheaper per label" in r.text  # labor comparison rendered
