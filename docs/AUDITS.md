# System Audits (for reviewers)

A short pass across four dimensions a reviewer asked about: performance, architecture, data quality, and system level compliance. Two themes recur. First, most of these questions have small answers here precisely because the system is stateless and deterministic by design, so there is less to audit. Second, where a real risk exists (reference data going stale), it is named and given an owner rather than hidden.

This memo summarizes and points to the detailed docs (`COST_AND_EFFICIENCY.md`, `SECURITY_AND_COMPLIANCE.md`, `MEMO.md`, `TECH_STACK.md`) rather than repeating them.

## 1. Performance audit

The hard target is a verdict in under 5 seconds per label. Measured behavior on the default model (`claude-haiku-4-5`):

| Stage | Typical time | Notes |
| --- | --- | --- |
| Image normalization (decode, EXIF strip, downscale, re-encode) | a few milliseconds | pure local CPU |
| Single Claude vision call | about 2.5 seconds warm | dominates the budget |
| Rule engine (all rules) plus verdict | well under a millisecond | pure functions, no I/O |
| Optional match check vs application JSON | sub millisecond | string comparison |

Finding: one stage dominates. The vision call is roughly 2.5 of the 2.7 seconds. Everything we wrote runs in milliseconds, so our own code is not the bottleneck and there is nothing to optimize there. The only real latency levers are:

1. Model choice. Haiku is the default for cost and speed; Sonnet is available via `CLAUDE_MODEL` when accuracy on a hard label matters more than latency.
2. Image downscale before the call (already done, capped at 1568 px), which cuts input tokens and therefore both cost and time.
3. Cold starts, removed by deploying on an always on tier plus a beverage selection landing step that primes the connection before the first upload.

Latency is instrumented: the real per label time is recorded and shown on the result page and aggregated (with a p95) on `/stats`. See `COST_AND_EFFICIENCY.md`.

## 2. Architecture audit

Organization, in one view (full detail in `MEMO.md`, `TECH_STACK.md`, `USER_FLOW.md`):

- **Shape.** A deterministic pipeline, not an agent: image to one vision call (perception) to a pure Python rule engine (judgment) to a PASS / FAIL / NEEDS REVIEW verdict with a CFR citation per field.
- **Where data lives.** Nowhere persistent. The app is stateless. An uploaded image exists only for the life of one request. The single on disk artifact is an append only cost metrics log (`metrics/usage.jsonl`, git ignored), which holds token counts, cost, and latency, no label content and no personal data.
- **Layer boundary that matters.** The model returns field values only; it never decides a verdict. That separation is the security boundary (a hijacked extraction cannot forge a PASS) and the testability boundary (the judgment layer is pure and provable for $0).
- **Integration points for new capability.** Two are explicit. To add wine or beer, add a rule module under `app/rules/` following the distilled spirits pattern and register it. To promote the warning Tier 2 checks (type size, bold, placement) from advisory to hard pass/fail, add vector PDF input, which carries real print specs a photo lacks.

## 3. Data quality audit (reference data freshness)

We hold no customer dataset, so the usual data quality concerns (missing fields, duplicate or stale records) do not apply in their usual form. The real data quality question here is whether the regulatory reference tables we encoded are current and correct, because a stale table becomes a wrong verdict.

| Reference table | Location | Source and last amended | Staleness risk if not updated |
| --- | --- | --- | --- |
| Authorized standards of fill | `app/rules/fill.py` (`AUTHORIZED_ML`) | 27 CFR 5.203, amended 2020 and January 2025 (T.D. TTB-200) | High: a newly legalized size would be wrongly FAILed. This is the table most worth watching. |
| Recognized class/type designations | `app/rules/classtype.py` (`RECOGNIZED`) | 27 CFR 5.141 to 5.143 | Low: an unrecognized term routes to NEEDS REVIEW, not FAIL, so a stale list causes extra human review, never a false failure. Fails safe by design. |
| Canonical Government Warning text | `app/rules/warning.py` (`CANONICAL`) | Alcoholic Beverage Labeling Act of 1988, 27 CFR 16.21 | High in principle, but the statutory text has been stable for decades. Change only if the statute changes. |

Two design choices reduce this risk. The class/type rule deliberately fails safe to review rather than failing a label outright. And the eval corpus imports the canonical warning text rather than copying it, so a fixture can never silently disagree with the rule.

Update procedure: when TTB amends a list, edit the single table, add a dated source comment, add or adjust an eval case in `evals/corpus.py`, and confirm `python -m evals.run_eval` still reports 100 percent.

On the extraction side, data quality means consistency of what the model reads off a photo. That is tested separately and manually with real bottle photos (the noisy, paid half), kept apart from the deterministic rule eval on purpose.

## 4. Compliance and regulatory audit (the system itself)

Distinguish two things. The compliance the tool checks (TTB label law) is the product, covered in `SECURITY_AND_COMPLIANCE.md`. The compliance the tool itself must meet as a system is below.

- **Data retention.** Minimal by design. No label image or applicant data is persisted; an upload lives for one request. The only retained artifact is a metrics log with no personal data. So there is almost nothing to retain or to expire.
- **Breach notification exposure.** Low for the same reason. The system stores no personal or sensitive data, strips EXIF (which can carry location), and keeps secrets out of code and out of git. A breach of this prototype would expose no applicant data because none is held.
- **Audit logging and decision auditability.** Every verdict is a deterministic function of the extracted fields and cites the controlling CFR section on the result page. The decision is reproducible and explainable, which is itself a strong audit property. Access logging and authentication are production concerns, noted as out of scope for the prototype in `SECURITY_AND_COMPLIANCE.md`.

Recommendation held to honestly: do not build a heavy retention or breach program for a prototype that stores no sensitive data. The right move is to document the posture (done here) and to keep the attack surface small, which a stateless design already does.
