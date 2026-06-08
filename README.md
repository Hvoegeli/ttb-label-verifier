# TTB Alcohol Label Verification (Prototype)

A web prototype that verifies U.S. distilled spirits labels against federal TTB
rules. An agent uploads a photo of a label; one Claude vision call reads the
regulated fields off the image; a deterministic Python rule engine checks those
fields against 27 CFR Parts 5 and 16; and the app returns a PASS / FAIL /
NEEDS REVIEW verdict with a plain reason and a CFR citation for every field.

Built as a take-home for a U.S. Treasury interview. Not an official TTB system;
results assist a human reviewer and are not final determinations.

## What it does

- Reads a label image (JPG, PNG, WebP, or HEIC) and extracts the regulated fields.
- Checks compliance with the in-force rules:
  - Government Warning present and verbatim, "GOVERNMENT WARNING" in capitals (27 CFR 16.21 / 16.22)
  - Net contents is an authorized standard of fill (27 CFR 5.203)
  - Alcohol content stated as percent alcohol by volume; proof optional (27 CFR 5.65)
  - Class/type is a recognized designation (27 CFR 5.141-5.143)
  - All mandatory elements present (27 CFR 5.63)
- Returns an overall verdict (FAIL beats NEEDS REVIEW beats PASS) with per-field
  reasons and citations.
- Measures and reports its own operating cost and latency at `/stats`.

## Architecture

A deterministic pipeline, not an agent. The model's only job is to read the
image into structured fields; it never decides PASS or FAIL. Every compliance
decision is made by pure, testable Python.

```
image upload -> normalize (JPEG, strip EXIF, downscale)
            -> one Claude vision call (forced tool-use -> typed JSON)
            -> deterministic rule engine (27 CFR Parts 5 + 16)
            -> PASS / FAIL / NEEDS REVIEW + per-field reasons + citations
```

See `docs/MEMO.md` for the design decisions and `docs/PRD.md` for requirements.

## Quickstart

Requires Python 3.11+ and an Anthropic API key.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then put your key in ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 and upload a label image.

## Configuration

Set in `.env` (see `.env.example`):

- `ANTHROPIC_API_KEY` (required)
- `CLAUDE_MODEL` (optional; defaults to `claude-haiku-4-5`, the cheapest vision
  model; set to `claude-sonnet-4-6` for higher accuracy at higher cost)
- `MAX_UPLOAD_MB` (optional, default 10)

## Tests

```bash
pytest
```

The vision model is mocked in the test suite, so tests are deterministic and
cost nothing. The rule engine has its own unit tests (`tests/test_rules.py`).

## Cost and efficiency

Each verification's real token cost is logged and surfaced at `/stats` (totals,
average cost per label, latency, and an adjustable labor-savings comparison).
Methodology and the cost-cutting design choices are in
`docs/COST_AND_EFFICIENCY.md`. Measured operating cost is on the order of a
fraction of a cent per label.

## Documentation

- `docs/PRD.md` - requirements and scope
- `docs/TECH_STACK.md` - stack and dependencies
- `docs/MEMO.md` - architecture decisions
- `docs/USER_FLOW.md` - user journey and endpoints
- `docs/TESTING_STRATEGY.md` - test plan and coverage
- `docs/SECURITY_AND_COMPLIANCE.md` - security measures and regulatory awareness
- `docs/COST_AND_EFFICIENCY.md` - cost methodology

## Scope and assumptions

- Distilled spirits only in this build; the rule engine is structured so wine
  (sulfite declaration) and beer (State-gated ABV) plug in.
- Image input only. Physical formatting checks on the warning (type size in mm,
  bold, contrasting background) cannot be proven from a photo and are shown as
  advisory; on true vector PDF artwork they would become hard checks (a
  documented production path).
- Proposed 2025 rules (allergen, nutrition, cancer warning) are not in force and
  are never treated as hard pass/fail gates.
- A production deployment behind TTB's firewall would swap cloud inference for a
  self-hosted model; this prototype uses the cloud API.

## Status

Working core: upload, extraction, the full distilled-spirits rule engine, the
overall verdict, and cost/efficiency reporting. In progress: the optional
label-vs-application match check, a public deployment, and the curated eval
label set.
