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
from app.extractor import ExtractedFields, ExtractionError, ExtractionResult
from app.main import _classify, app
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


# ---- _classify (rule set + how it was decided) ----

def test_classify_explicit_selection_is_forced():
    assert _classify("spirits", "wine") == ("spirits", "forced")


def test_classify_uses_detected_when_auto():
    assert _classify("auto", "wine") == ("wine", "detected")
    assert _classify("auto", "beer") == ("beer", "detected")


def test_classify_undetermined_falls_back_to_spirits():
    # Null or out-of-enum detection under auto: spirits is only a default book,
    # and the source is flagged undetermined so the caller routes to review.
    assert _classify("auto", None) == ("spirits", "undetermined")
    assert _classify("auto", "cider") == ("spirits", "undetermined")


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
    assert "you selected this type" in r.text
    assert "the label otherwise reads as wine" in r.text
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


# ---- review fixes: honest type-source reporting ----

def _spirits_fields(**over):
    """A compliant spirits read; beverage_type controllable for routing tests."""
    return _result(brand_name="OLD TOM DISTILLERY",
                   class_type="Kentucky Straight Bourbon Whiskey",
                   alcohol_content="45% Alc./Vol. (90 Proof)", net_contents="750 mL",
                   name_and_address="Bottled by Old Tom, Bardstown, KY", **over)


def test_failed_read_does_not_claim_a_type(monkeypatch):
    # Issue 1: a total extraction failure must NOT render "Checked as <type>".
    def boom(*a, **k):
        raise ExtractionError("The label-reading service was unavailable. Please try again.")
    monkeypatch.setattr(main_module, "extract_fields", boom)
    r = client.post("/verify", files=_file(), data={"beverage": "auto"})
    assert r.status_code == 200
    assert "NEEDS REVIEW" in r.text
    assert "Checked as" not in r.text          # no fabricated classification
    assert "unavailable" in r.text


def test_undetermined_type_routes_to_review(monkeypatch):
    # Issue 3: auto mode + no usable detected type -> NEEDS REVIEW, not silent spirits PASS.
    monkeypatch.setattr(main_module, "extract_fields", lambda *a, **k: _spirits_fields(beverage_type=None))
    r = client.post("/verify", files=_file(), data={"beverage": "auto"})
    assert r.status_code == 200
    assert "NEEDS REVIEW" in r.text
    assert "could not be determined" in r.text


def test_out_of_enum_type_routes_to_review(monkeypatch):
    # Issue 3: a populated but out-of-enum type ("cider") is treated as undetermined.
    monkeypatch.setattr(main_module, "extract_fields", lambda *a, **k: _spirits_fields(beverage_type="cider"))
    r = client.post("/verify", files=_file(), data={"beverage": "auto"})
    assert r.status_code == 200
    assert "NEEDS REVIEW" in r.text
    assert "could not be determined" in r.text


def test_explicit_pick_is_not_mislabeled_as_auto(monkeypatch):
    # Issue 5: forcing wine on a wine label must say "you selected", not "detected".
    monkeypatch.setattr(main_module, "extract_fields", lambda *a, **k: _wine())
    r = client.post("/verify", files=_file(), data={"beverage": "wine"})
    assert r.status_code == 200
    assert "you selected this type" in r.text
    assert "detected automatically" not in r.text


def test_batch_forced_rows_marked_forced(monkeypatch):
    # Issue 2: a forced batch shows "(forced)" so a coerced row is not read as detected.
    monkeypatch.setattr(main_module, "extract_fields", lambda *a, **k: _spirits())
    files = [("images", (f"l{i}.png", _png(), "image/png")) for i in range(2)]
    r = client.post("/batch", files=files, data={"beverage": "wine"})
    assert r.status_code == 200
    assert "(forced)" in r.text


def test_batch_undetermined_shows_not_determined(monkeypatch):
    # Issue 1/2: an undetermined label shows "Not determined", not a fabricated type.
    monkeypatch.setattr(main_module, "extract_fields", lambda *a, **k: _spirits_fields(beverage_type=None))
    files = [("images", ("l.png", _png(), "image/png"))]
    r = client.post("/batch", files=files, data={"beverage": "auto"})
    assert r.status_code == 200
    assert "Not determined" in r.text


def test_wine_match_fields_ignored_for_non_wine(monkeypatch):
    # Issue 5: a wine-only application field filed against a spirits label must not
    # produce a spurious match row; with only that field, no match block appears.
    monkeypatch.setattr(main_module, "extract_fields", lambda *a, **k: _spirits())
    r = client.post("/verify", files=_file(),
                    data={"beverage": "auto", "app_appellation": "Napa Valley"})
    assert r.status_code == 200
    assert "Label vs Application" not in r.text
