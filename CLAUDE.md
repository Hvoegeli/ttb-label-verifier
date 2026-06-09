# CLAUDE.md: TTB Label Verification App

Project guardrails for AI assisted work in this repo. These supplement Harrison's global instructions.

## Project at a glance

A deterministic pipeline web app: upload a distilled spirits label image, one Claude vision call extracts the regulated fields, a pure Python rule engine checks them against 27 CFR Parts 5 and 16, and the app returns PASS / FAIL / NEEDS REVIEW with a CFR citation per field. See `docs/` for the full PRD, tech stack, architecture memo, user flow, and testing strategy. The project context lives in `presearch.md`.

## Environment Protection
- Never modify `.env` without user confirmation.
- Never commit `.env` files (only `.env.example` if one is created).
- Never display API key values or hardcode secrets anywhere in the code.

## Error Logging
- Log build failures, runtime errors, API errors, deployment errors, and anything that took more than five minutes to diagnose to `docs/ERROR_FIX_LOG.md`.
- Do NOT log typos, linter warnings, or expected test failures.

## Tech Stack Lock

Locked decisions from presearch. Do not switch any of these without explicit user approval. New dependencies require justification.

- Language: Python 3.11+
- Web framework: FastAPI (single deployable app)
- Server: Uvicorn
- Templates: Jinja2 + vanilla JS (no SPA, no build step)
- Vision: Anthropic Claude via the official `anthropic` Python SDK, using tool-use to force structured JSON extraction
- Rule engine: plain Python pure functions (no agent framework: no LangChain, LangGraph, or CrewAI)
- Tests: pytest
- Hosting: Render (persistent web service)
- Dependencies: pip + requirements.txt

## Compliance correctness rules
- The Government Warning wording is compared verbatim per 27 CFR 16.21, normalizing whitespace and ignoring letter case. An all-capitals warning is compliant and is what most real bottles print (confirmed against real labels 2026-06-08); 27 CFR 16.22 mandates only that the words "GOVERNMENT WARNING" be in capital letters, which IS enforced separately. Never strip punctuation. Bold weight cannot be verified from a photo and stays a Tier 2 advisory.
- Standards of fill must match the authorized list in 27 CFR 5.203; keep the list sourced and dated (amended 2020 and January 2025).
- Percent alcohol by volume is the mandatory alcohol statement (27 CFR 5.65); proof is optional and never a substitute.
- The vision model never decides PASS or FAIL. It only returns field values. All verdicts come from deterministic code.
- Proposed rules (allergen, Alcohol Facts nutrition, cancer warning) are advisory only and must never be hard pass/fail gates.
- Country of origin (27 CFR 5.69 / 7.69, deferring to CBP marking at 19 CFR part 134) is conditional on the product being an import. Because import status is hard to prove from one photo, this check never hard-FAILs on that inference: it returns NEEDS REVIEW when the label looks imported but states no origin, and PASS otherwise. Do not turn it into an auto-FAIL.
- When a field cannot be read with confidence, return NEEDS REVIEW. Never auto pass.

## Workflow rules (from global instructions)
- Work on a feature branch; leave main untouched unless told otherwise.
- Run `/correct` before commits and pushes.
- Audit gate before delivery: `/correct`, then `/security-review`, then `/ship-check`.
- Do not bypass safety checks (no `--no-verify`, `--force`, etc.) before they have run.
- Written prose in deliverables (README, docs) avoids dashes per Harrison's standing preference.
