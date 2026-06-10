"""Tests for confidence-based escalation in the extractor.

The single-call helper (_extract_once) is mocked, so no real model runs. These
prove that a low-confidence or likely-misread first pass triggers exactly one
re-read with the stronger model, the cost is summed, and the feature respects its
config flag.
"""
import app.extractor as extractor
from app.extractor import ExtractionResult, _should_escalate, extract_fields
from app.models import ExtractedFields
from app.rules.warning import CANONICAL

HAIKU = "claude-haiku-4-5"
SONNET = "claude-sonnet-4-6"


def _fields(**over):
    base = dict(
        brand_name="NORTH CREEK", class_type="Vodka", alcohol_content="40% Alc/Vol",
        net_contents="750 mL", name_and_address="North Creek, Austin, TX",
        government_warning=CANONICAL, warning_legible=True, overall_legible=True,
    )
    base.update(over)
    return ExtractedFields(**base)


def _result(model, **fover):
    return ExtractionResult(fields=_fields(**fover), input_tokens=1000, output_tokens=200,
                            cost_usd=0.01, model=model)


def _wire(monkeypatch, fake, enabled=True):
    monkeypatch.setattr(extractor.settings, "claude_model", HAIKU)
    monkeypatch.setattr(extractor.settings, "escalation_model", SONNET)
    monkeypatch.setattr(extractor.settings, "enable_escalation", enabled)
    monkeypatch.setattr(extractor, "_extract_once", fake)


def test_should_escalate_triggers():
    assert _should_escalate(_fields(overall_legible=False)) is True
    assert _should_escalate(_fields(warning_legible=False)) is True
    assert _should_escalate(_fields(government_warning=CANONICAL.replace("machinery", "machinary"))) is True
    assert _should_escalate(_fields()) is False


def test_escalates_on_low_confidence(monkeypatch):
    calls = []

    def fake(images, model):
        calls.append(model)
        return _result(model, overall_legible=False) if model == HAIKU else _result(model)

    _wire(monkeypatch, fake)
    res = extract_fields([b"x"])
    assert calls == [HAIKU, SONNET]
    assert res.escalated is True
    assert res.model == f"{HAIKU}+{SONNET}"
    assert abs(res.cost_usd - 0.02) < 1e-9  # both calls summed


def test_escalates_on_warning_mismatch(monkeypatch):
    calls = []
    garbled = CANONICAL.replace("health problems.", "health issues.")

    def fake(images, model):
        calls.append(model)
        return _result(model, government_warning=garbled) if model == HAIKU else _result(model)

    _wire(monkeypatch, fake)
    res = extract_fields([b"x"])
    assert calls == [HAIKU, SONNET]
    assert res.escalated is True


def test_no_escalation_on_clean_read(monkeypatch):
    calls = []

    def fake(images, model):
        calls.append(model)
        return _result(model)

    _wire(monkeypatch, fake)
    res = extract_fields([b"x"])
    assert calls == [HAIKU]
    assert res.escalated is False
    assert res.model == HAIKU


def test_escalation_can_be_disabled(monkeypatch):
    calls = []

    def fake(images, model):
        calls.append(model)
        return _result(model, overall_legible=False)

    _wire(monkeypatch, fake, enabled=False)
    res = extract_fields([b"x"])
    assert calls == [HAIKU]
    assert res.escalated is False


def test_escalation_failure_keeps_primary(monkeypatch):
    def fake(images, model):
        if model == HAIKU:
            return _result(model, overall_legible=False)
        raise extractor.ExtractionError("escalation unavailable")

    _wire(monkeypatch, fake)
    res = extract_fields([b"x"])
    assert res.escalated is False  # fell back to the primary read
    assert res.model == HAIKU
