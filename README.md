# TTB Alcohol Label Verification (Prototype)

A web prototype that verifies U.S. alcohol beverage labels against federal TTB
rules. An agent picks a beverage type (distilled spirits, wine, or malt
beverage), uploads a photo of the label; one Claude vision call reads the
regulated fields off the image; a deterministic Python rule engine checks those
fields against the right regulations (27 CFR Part 5 for spirits, Part 4 for wine,
Part 7 for malt beverages, and Part 16 for the health warning); and the app
returns a PASS / FAIL / NEEDS REVIEW verdict with a plain reason and a CFR
citation for every field.

Built as a take-home for a U.S. Treasury interview. Not an official TTB system;
results assist a human reviewer and are not final determinations.

## What it does

- Reads a label image (JPG, PNG, WebP, or HEIC), front and optional back, and
  extracts the regulated fields.
- Runs the rule set for the chosen beverage. For distilled spirits, the in-force
  checks are:
  - Government Warning present with the required wording, "GOVERNMENT WARNING" in capitals (27 CFR 16.21 / 16.22)
  - Net contents is an authorized standard of fill (27 CFR 5.203)
  - Alcohol content stated as percent alcohol by volume; proof optional (27 CFR 5.65)
  - Class/type is a recognized designation (27 CFR 5.141-5.143)
  - All mandatory elements present (27 CFR 5.63)
  - Wine (Part 4) and malt beverages (Part 7) have their own rule sets with the
    differences noted under Scope below.
- Returns an overall verdict (FAIL beats NEEDS REVIEW beats PASS) with per-field
  reasons and citations. Mandatory checks are badged Golden Rules; advisory
  checks (like the wine sulfite declaration) never change the verdict.
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

## Tests and evaluation

```bash
pytest                     # full suite: unit tests + the eval corpus
python -m evals.run_eval   # known-answer eval report (per-case table + accuracy)
```

The vision model is mocked in the test suite, so every test is deterministic and
costs nothing. Three layers:

- **Rule unit tests** (`tests/test_rules.py`): each rule function in isolation.
- **Golden set eval** (`evals/`): 52 known-answer "mutant" labels, each a single
  planted change from a compliant baseline, run through the real rule engine.
  `run_eval` reproduces 52/52 verdicts at $0 and writes `evals/results.json`.
- **App tests** (`tests/test_app.py`): routes, upload validation, and rendering.

A regression is caught two ways. A GitHub Actions workflow runs the suite and the
eval on every pull request and push to main (`.github/workflows/ci.yml`), and a
local pre-push hook (`.githooks/pre-push`, activate with
`git config core.hooksPath .githooks`) runs the suite before any push. Both are
keyless and free. The deterministic gate is held to 100 percent, no regressions;
the noisier extraction accuracy (model reading real photos) is a separate manual
check by design.

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
- `docs/AUDITS.md` - performance, architecture, data freshness, and system compliance audits
- `evals/README.md` - how the known-answer eval corpus works

## Scope and assumptions

- Three beverage types are supported, each with its own rule set: distilled
  spirits (27 CFR Part 5), wine (Part 4, including its own standards of fill, the
  table-wine alcohol exception, the conditional appellation, and an advisory
  sulfite check), and malt beverages (Part 7, with no standards of fill, optional
  alcohol content, and the "ABV" abbreviation rule). The Government Warning
  (Part 16) is shared by all three.
- Image input only. Physical formatting checks on the warning (type size in mm,
  bold, contrasting background) cannot be proven from a photo and are shown as
  advisory; on true vector PDF artwork they would become hard checks (a
  documented production path).
- Proposed 2025 rules (allergen, nutrition, cancer warning) are not in force and
  are never treated as hard pass/fail gates.
- A production deployment behind TTB's firewall would swap cloud inference for a
  self-hosted model; this prototype uses the cloud API.

## Status

Working core: upload (front and optional back), extraction, rule engines for all
three beverages (distilled spirits, wine, malt beverages), the overall verdict,
the optional label-vs-application match check, a loading indicator during the
model call, the 71-case golden set eval with a CI gate, and cost/efficiency
reporting. In progress: a public deployment and a manual extraction eval on real
bottle photos.
