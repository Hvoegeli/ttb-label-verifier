# Cost and Efficiency

This document explains how the prototype measures its own operating cost, the
deliberate engineering choices that keep that cost low, and how to audit every
figure. It is written for a reviewer evaluating cost-effectiveness, so the
emphasis is on measured numbers and transparent methodology, not estimates.

## How cost is measured (not estimated)

Every live verification calls the vision model once. The API returns the exact
token usage for that call. The app multiplies that usage by the model's
published per-token price and appends a record to an append-only log
(`metrics/usage.jsonl`). The live `/stats` page reads that log and reports totals,
average cost per label, and latency percentiles.

- Pricing table (dated and sourced) lives in `app/costs.py` (`PRICING`), confirmed
  against the Anthropic pricing reference (2026-05-26).
- Cost per call = `input_tokens / 1e6 * input_price + output_tokens / 1e6 * output_price`.
- Nothing is back-estimated: the numbers come from the API's own usage report.

To audit: run the app, verify a few labels, then open `/stats` or read
`metrics/usage.jsonl` directly (one JSON object per call).

## Per-label cost breakdown

A normalized label image is roughly 1,600 image tokens, plus about 500 tokens of
prompt and tool schema in, and about 400 tokens of structured JSON out. On the
default model (Claude Haiku 4.5, $1.00 input / $5.00 output per 1M tokens) that is
on the order of **$0.004 to $0.005 per label**. The `/stats` page shows the actual
measured average for this deployment.

## Representative measured run (the sample labels)

Running the committed sample label set through the live pipeline on Claude Haiku
4.5 produced the measured figures below. The snapshot was taken on the 25-label
set (10 pass, 10 fail, 5 review); the corpus has since grown to 27 with two
imported-product labels added for the country-of-origin check (now 11 pass, 10
fail, 6 review), which does not materially change the per-label cost or latency.
This is a snapshot for a reader who does not run the app; the live `/stats` page
shows whatever the current deployment has actually processed.

| Measure | Value |
| --- | --- |
| Labels processed | 25 |
| Verdict split | 10 PASS, 10 FAIL, 5 NEEDS REVIEW |
| Triage | 40% cleared, 60% flagged for a person |
| Average cost per label | $0.0037 |
| Total cost (25 labels) | $0.0927 |
| Average latency | 3.6 s |
| 95th percentile latency | 5.7 s |
| Model | claude-haiku-4-5 |

The triage figure is the efficiency argument in one line: the tool cleared 40% of
the volume outright and concentrated human attention on the 60% it flagged, rather
than every reviewer reading every label from scratch. A reviewer still spot-checks
a sample of the cleared labels (see the human-in-the-loop note in
`SECURITY_AND_COMPLIANCE.md`), so the saving is on routine screening, not a removal
of human judgment.

The 95th-percentile latency here (5.7 s) slightly exceeds the 5 s warm target
because these were back-to-back batch calls including a cold first call; the
per-label average stays at 3.6 s. The 5 s target describes a warmed, always-on
deployment, which is how the public demo is hosted.

## Engineering choices that cut cost

| Decision | Effect |
| --- | --- |
| **Default to Claude Haiku 4.5** instead of Sonnet or Opus | Haiku is $1/$5 per 1M tokens, vs Sonnet $3/$15 (3x) and Opus $5/$25 (5x). In live testing Haiku transcribed the Government Warning verbatim on clean labels, so the cheapest model met the accuracy bar for the common case. |
| **Confidence-based escalation, not a blanket upgrade** | Rather than run every label on the expensive model, the cheap model reads first and the label is re-read on Sonnet only when the first read is low confidence or the warning does not match the statute (a likely misread). The 3x cost is paid only on the minority of hard labels, so average cost stays near the Haiku figure while accuracy on the hard cases improves. Set `ENABLE_ESCALATION=false` to disable. |
| **Downscale images to 1568px long edge** | Image token cost scales with pixel count. 1568px is the documented efficiency ceiling (larger images are resized server-side anyway), so full-resolution phone photos do not inflate cost. |
| **One model call, no agent framework** | A deterministic pipeline makes exactly one inference call per label. No agent loop, no chained calls, no repeated tool round-trips, each of which would multiply tokens. |
| **Capped output tokens** (`max_tokens = 1024`) | The structured JSON is small; the cap prevents a runaway response from consuming budget. |
| **Deterministic rule engine, not the model, makes verdicts** | Compliance checks run in plain Python at effectively zero marginal cost. The expensive model is used only for the one thing it is needed for: reading the image. |
| **Model mocked in the entire test suite** | CI and unit tests cost $0 in API spend while still exercising every code path. |
| **No prompt caching** | Considered and rejected: the cacheable-prefix minimum on Haiku (4,096 tokens) exceeds our small prompt, so caching would not engage. Documented so the choice is visible, not an oversight. |
| **Confidence gate routes unreadable images to human review** | Avoids paying for repeated model calls on images the model cannot read; the agent is asked for a better photo instead. |

## Latency (efficiency)

The prior vendor lost adoption because it sometimes took 30 to 40 seconds per
label. The target here is under 5 seconds per label (warm, 95th percentile), and
the app measures and displays the actual processing time on every result and in
aggregate on `/stats`. Cold starts are removed for reviewers by running on an
always-on host plus priming the model on the landing step, so the measured latency
reflects steady-state operation.

## Labor comparison (illustrative, adjustable)

The `/stats` page contrasts the measured automated cost per label with an
illustrative manual cost. The manual cost uses two assumptions a reviewer can set
themselves via the query string (`?minutes_per_label=NN&hourly_rate=NN`):

- minutes per manual review (default 7.5, the midpoint of the 5 to 10 minutes
  cited in discovery)
- loaded hourly rate (default $50, a placeholder; set it to your own GS-grade
  loaded figure)

`manual_cost_per_label = (minutes / 60) * hourly_rate`. The automated cost is the
real measured average. The page also projects both to TTB's stated volume of
150,000 applications per year.

**Honesty caveat:** the tool assists agents on the routine matching that consumes
much of their day; it does not replace human judgment, and it does not auto-approve.
The labor figures therefore illustrate time saved on routine review, not headcount
replacement. The automated cost is real; the manual cost is an assumption you
control. This separation is deliberate so the comparison can be audited rather than
taken on faith.

## Reproduce / audit

1. Set `ANTHROPIC_API_KEY` in `.env`.
2. Run the app, verify several labels (real or generated).
3. Open `/stats` for the aggregate, or read `metrics/usage.jsonl` for the raw
   per-call records.
4. Cross-check any record's `cost_usd` against `PRICING` in `app/costs.py`.
