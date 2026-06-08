"""Smoke tests for the app shell (Task Groups 1 and 2).

These exercise the routes and the image normalization. They do not call the
Claude model (that arrives in Task Group 3 and will be mocked in CI).
"""
import io

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

client = TestClient(app)


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


def test_verify_accepts_valid_image():
    files = {"image": ("label.png", _png_bytes(), "image/png")}
    r = client.post("/verify", files=files, data={"beverage": "spirits"})
    assert r.status_code == 200
    # Result skeleton renders with the pending notice until extraction lands.
    assert "PENDING" in r.text


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
