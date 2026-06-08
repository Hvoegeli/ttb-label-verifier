"""Tests for the batch verification path (POST /batch).

The vision model is mocked, so these are deterministic and free. They prove:
  - the aggregate genuinely mixes verdicts (not one result counted N times),
  - the measured cost rolls up and projects out to larger volumes,
  - one bad photo becomes a NEEDS REVIEW row instead of aborting the batch,
  - the empty and over-cap guards reject before any model call.
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
    return ExtractionResult(
        fields=_fake_fields(**overrides),
        input_tokens=2100,
        output_tokens=400,
        cost_usd=0.0042,
    )


def _png_bytes(size=(60, 40), color=(200, 120, 40)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _img(name):
    return ("images", (name, _png_bytes(), "image/png"))


def test_batch_page_renders():
    r = client.get("/batch?beverage=spirits")
    assert r.status_code == 200
    assert "Batch verify" in r.text
    assert "up to 25" in r.text  # default cap surfaced to the user


def test_batch_mixes_verdicts_and_projects(monkeypatch):
    # Three labels, three different outcomes, driven by call order.
    calls = {"n": 0}

    def fake(images, beverage="spirits"):
        calls["n"] += 1
        if calls["n"] == 1:
            return _fake_result()                          # compliant -> PASS
        if calls["n"] == 2:
            return _fake_result(net_contents="800 mL")     # illegal fill -> FAIL
        return _fake_result(overall_legible=False)         # unreadable -> NEEDS REVIEW

    monkeypatch.setattr(main_module, "extract_fields", fake)
    files = [_img("pass.png"), _img("fail.png"), _img("review.png")]
    r = client.post("/batch", files=files, data={"beverage": "spirits"})

    assert r.status_code == 200
    # Every label appears, and all three verdicts are present in the table.
    for name in ("pass.png", "fail.png", "review.png"):
        assert name in r.text
    assert "PASS" in r.text
    assert "FAIL" in r.text
    assert "NEEDS REVIEW" in r.text
    # Projection section reaches TTB's stated annual volume.
    assert "What this means at scale" in r.text
    assert "150,000" in r.text


def test_batch_cost_rolls_up_and_projects(monkeypatch):
    # Two compliant labels at $0.0042 each: total $0.0084, projected 300 -> $1.26.
    monkeypatch.setattr(main_module, "extract_fields", lambda *a, **k: _fake_result())
    files = [_img("a.png"), _img("b.png")]
    r = client.post("/batch", files=files, data={"beverage": "spirits"})
    assert r.status_code == 200
    assert "0.0084" in r.text   # total cost
    assert "1.26" in r.text     # 300-label projection from the measured average


def test_batch_one_bad_file_becomes_review_not_abort(monkeypatch):
    # A non-image file must not abort the run; it becomes a NEEDS REVIEW row and
    # the valid label is still verified.
    monkeypatch.setattr(main_module, "extract_fields", lambda *a, **k: _fake_result())
    files = [
        _img("good.png"),
        ("images", ("notes.txt", b"hello", "text/plain")),
    ]
    r = client.post("/batch", files=files, data={"beverage": "spirits"})
    assert r.status_code == 200
    assert "good.png" in r.text
    assert "notes.txt" in r.text
    assert "Unsupported file type" in r.text  # the bad row's reason
    assert "PASS" in r.text                    # the good label still passed


def test_batch_extraction_error_row_does_not_abort(monkeypatch):
    # If the model call fails for one label, that row routes to review and the
    # rest of the batch still completes.
    calls = {"n": 0}

    def fake(images, beverage="spirits"):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ExtractionError("The label-reading service was unavailable. Please try again.")
        return _fake_result()

    monkeypatch.setattr(main_module, "extract_fields", fake)
    files = [_img("one.png"), _img("two.png"), _img("three.png")]
    r = client.post("/batch", files=files, data={"beverage": "spirits"})
    assert r.status_code == 200
    assert "unavailable" in r.text
    for name in ("one.png", "two.png", "three.png"):
        assert name in r.text


def test_batch_empty_is_rejected():
    # No files at all -> a clear message, no processing.
    r = client.post("/batch", data={"beverage": "spirits"})
    assert r.status_code == 400
    assert "at least one" in r.text


def test_batch_over_cap_is_rejected(monkeypatch):
    monkeypatch.setattr(main_module.settings, "max_batch", 1)
    files = [_img("a.png"), _img("b.png")]
    r = client.post("/batch", files=files, data={"beverage": "spirits"})
    assert r.status_code == 400
    assert "up to 1 labels" in r.text


def test_batch_records_each_label_cost(monkeypatch):
    # Each processed label appends one metrics record, so /stats stays accurate.
    monkeypatch.setattr(main_module, "extract_fields", lambda *a, **k: _fake_result())
    files = [_img("a.png"), _img("b.png"), _img("c.png")]
    client.post("/batch", files=files, data={"beverage": "spirits"})
    agg = costs_module.aggregate()
    assert agg["count"] == 3
    assert abs(agg["total_cost_usd"] - 0.0126) < 1e-9
