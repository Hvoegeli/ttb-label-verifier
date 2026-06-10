"""Tests for beverage auto-detection and rule routing (app/main.py).

The vision read now classifies the beverage type, and the pipeline routes each
label to the matching rule set unless the user forces one. The model is mocked,
so these are deterministic and free. They prove the core friction fix: a wine or
beer label is judged by its own rules, not whichever type the user happened to
pick, and a mixed batch routes each label independently.
"""
import io
import itertools

from fastapi.testclient import TestClient
from PIL import Image

import app.main as main_module
from app.extractor import ExtractedFields, ExtractionResult
from app.main import _resolve_beverage, app
from app.rules.warning import CANONICAL

client = TestClient(app)


def _png(color=(200, 120, 40)):
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), color).save(buf, format="PNG")
    return buf.getvalue()


def _file(name="label.png"):
    return {"image": (name, _png(), "image/png")}


def _result(**fields):
    return ExtractionResult(
        fields=ExtractedFields(government_warning=CANONICAL, warning_legible=True,
                               overall_legible=True, **fields),
        input_tokens=1000, output_tokens=200, cost_usd=0.004,
    )


def _wine():
    return _result(beverage_type="wine", brand_name="STONECREST CELLARS",
                   class_type="Cabernet Sauvignon", alcohol_content="13.5% Alc./Vol.",
                   net_contents="750 mL", name_and_address="Bottled by Stonecrest, Napa, CA",
                   appellation="Napa Valley", vintage="2019", grape_varietal="Cabernet Sauvignon",
                   sulfite_statement="Contains Sulfites")


def _spirits():
    return _result(beverage_type="spirits", brand_name="OLD TOM DISTILLERY",
                   class_type="Kentucky Straight Bourbon Whiskey",
                   alcohol_content="45% Alc./Vol. (90 Proof)", net_contents="750 mL",
                   name_and_address="Bottled by Old Tom, Bardstown, KY")


def _beer():
    return _result(beverage_type="beer", brand_name="RIVERBED BREWING",
                   class_type="India Pale Ale", alcohol_content="6.5% Alc/Vol",
                   net_contents="12 FL OZ", name_and_address="Brewed by Riverbed, Portland, OR",
                   is_flavored_malt_beverage=False)


# ---- _resolve_beverage ----

def test_resolve_explicit_selection_overrides():
    assert _resolve_beverage("spirits", "wine") == "spirits"


def test_resolve_uses_detected_when_auto():
    assert _resolve_beverage("auto", "wine") == "wine"
    assert _resolve_beverage("auto", "beer") == "beer"


def test_resolve_falls_back_to_spirits():
    assert _resolve_beverage("auto", None) == "spirits"
    assert _resolve_beverage("auto", "nonsense") == "spirits"


# ---- single-label routing ----

def test_auto_detected_wine_judged_by_wine_rules(monkeypatch):
    # The whole point: a Cabernet detected as wine passes under WINE rules. Under
    # spirits rules it would be flagged NEEDS REVIEW for an unrecognized class/type.
    monkeypatch.setattr(main_module, "extract_fields", lambda *a, **k: _wine())
    r = client.post("/verify", files=_file(), data={"beverage": "auto"})
    assert r.status_code == 200
    assert "Checked as <strong>Wine" in r.text
    assert "detected automatically" in r.text
    assert "PASS" in r.text


def test_auto_detected_beer_judged_by_beer_rules(monkeypatch):
    monkeypatch.setattr(main_module, "extract_fields", lambda *a, **k: _beer())
    r = client.post("/verify", files=_file(), data={"beverage": "auto"})
    assert r.status_code == 200
    assert "Checked as <strong>Malt Beverage" in r.text
    assert "PASS" in r.text


def test_forced_type_overrides_detection_and_is_noted(monkeypatch):
    # Force spirits on a wine label: spirits rules run (so the Cabernet class/type
    # is unrecognized -> NEEDS REVIEW) and the override is surfaced to the user.
    monkeypatch.setattr(main_module, "extract_fields", lambda *a, **k: _wine())
    r = client.post("/verify", files=_file(), data={"beverage": "spirits"})
    assert r.status_code == 200
    assert "Checked as <strong>Distilled Spirits" in r.text
    assert "you chose this type" in r.text
    assert "NEEDS REVIEW" in r.text


# ---- mixed batch ----

def test_mixed_batch_routes_each_label_by_its_type(monkeypatch):
    # Three labels of three types under auto: each must be judged by its own rules
    # (all PASS) and its detected type shown. Concurrency-safe counter assigns types.
    counter = itertools.count()
    results = [_wine(), _spirits(), _beer()]

    def fake(images, *a, **k):
        return results[next(counter) % 3]

    monkeypatch.setattr(main_module, "extract_fields", fake)
    files = [("images", (f"l{i}.png", _png(), "image/png")) for i in range(3)]
    r = client.post("/batch", files=files, data={"beverage": "auto"})
    assert r.status_code == 200
    # Every type appears in the table, and none was flagged (all routed correctly).
    assert "Wine" in r.text
    assert "Distilled Spirits" in r.text
    assert "Malt Beverage" in r.text
    # Row verdict pills tell the real story (the words FAIL/REVIEW also appear in
    # boilerplate). All three rows passed, so only pass pills should be present.
    assert "verdict-pill verdict-pass" in r.text
    assert "verdict-pill verdict-fail" not in r.text
    assert "verdict-pill verdict-needs-review" not in r.text
