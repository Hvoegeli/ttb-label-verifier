# Product Requirements Document: TTB Alcohol Label Verification App

## Overview

A web prototype that lets a TTB compliance agent upload a photo of a distilled spirits label, automatically reads the regulated fields off the image, and returns a clear PASS / FAIL / NEEDS REVIEW verdict with a plain reason and a CFR citation for every field it checks.

## Problem Statement

TTB reviews roughly 150,000 label applications a year with a small team. A large share of that work is routine matching: confirming the brand name, alcohol content, and government warning on the label match the application and satisfy federal rules. Agents do this by eye, one label at a time. A prior automated vendor was not adopted because it sometimes took 30 to 40 seconds to process a single label, and agents could check five by eye in that time. The lesson: the occasional slow result, not the average, is what loses users. The opportunity is a fast assistant that handles the routine checks so agents spend their judgment on the genuinely hard cases.

## Target Users

TTB compliance agents of widely varying technical comfort. Half the team is over 50. The benchmark stated in discovery was "something my 73 year old mother could use." The interface must be clean and obvious with no hunting for buttons. The tool assists the agent; it never makes the final call on its own.

## Scope: what "verify" means here

The app does two complementary checks on every uploaded label:

1. **Compliance check (the spine):** does the label satisfy the in force TTB rules in 27 CFR Parts 5 and 16? This is the harder, more valuable check and the primary build.
2. **Match check (thin second pass):** do the extracted fields match the values on a mock application form? This mirrors the "data entry verification" agents do today and reuses the fields already extracted for the compliance check.

## MVP Requirements

- [MVP1] **Single image upload, multiple formats in, one format internally.** Accept one distilled spirits label image as JPG/JPEG, PNG, WebP, or HEIC through a simple web form. Normalize every upload on intake: re-encode to JPEG (also defuses malformed/polyglot files), strip EXIF metadata (GPS, device, timestamp), downscale oversized images (protects latency and limits resource exhaustion), and enforce a size limit and type allowlist. HEIC is supported because phone cameras default to it. Reject other types with a plain message. See `docs/SECURITY_AND_COMPLIANCE.md`.
- [MVP2] **Field extraction.** One Claude vision call returns the regulated fields as structured JSON: brand name, class/type designation, alcohol content, net contents, name and address, and the government warning text. Each field carries an extraction confidence signal.
- [MVP3] **Government Warning check (two tiers).** The warning rule is split by what an image can actually prove.
  - **Tier 1 (hard pass/fail, image provable):** the warning is present, verbatim per 27 CFR 16.21 (both numbered sentences, exact wording), with "GOVERNMENT WARNING:" in capital letters. Byte exact comparison after normalizing whitespace only. These drive the verdict. On any mismatch the result renders a character level diff (label text versus statute text) so the agent can confirm a real alteration or override an OCR glitch in one glance. The model is instructed to transcribe the warning exactly and flag any portion it cannot read clearly; flagged or garbled portions route to NEEDS REVIEW, while clean but non-verbatim text is FAIL. Known limitation: small print OCR can misread a word and return it confidently; the visible diff plus human override is the mitigation.
  - **Tier 2 (advisory, "cannot verify from image"):** bold weight, minimum type size in mm (27 CFR 16.22(b): 1 mm for containers up to 237 mL, 2 mm up to 3 L, 3 mm above), contrasting background, and separate and apart placement. Shown to the agent as informational, with the correct mm threshold for the detected container size, never as an automated FAIL. These can become hard checks only on a true vector PDF input (see production path).
- [MVP4] **Standards of fill check.** Validate the net contents value is an authorized distilled spirits size per 27 CFR 5.203 (for example 750 mL is valid; 800 mL is not).
- [MVP5] **Alcohol content format check.** Validate alcohol content is stated as a percentage of alcohol by volume in an accepted format per 27 CFR 5.65; treat proof as optional and allowed only alongside the percent statement.
- [MVP6] **Class/type check.** Validate a class or type designation is present and is a recognized standard of identity term per 27 CFR 5.141 to 5.143 (for example "Kentucky Straight Bourbon Whiskey").
- [MVP7] **Mandatory field presence check.** Confirm all required elements for distilled spirits are present per 27 CFR 5.63 (brand name, class/type, alcohol content, net contents, name and address, warning).
- [MVP8] **Verdict assembly.** Produce an overall PASS / FAIL / NEEDS REVIEW result plus a per field breakdown, each line stating the rule outcome, a plain language reason, and the controlling CFR citation.
  - **Per field states:** PASS (read clearly, satisfies the rule); FAIL (read clearly, violates a hard rule); NEEDS REVIEW (could not be read confidently, or the rule is judgment based / Tier 2 advisory / an unrecognized but plausible value).
  - **Aggregation priority (FAIL beats REVIEW beats PASS):** overall FAIL if any hard field is a confident FAIL; else overall NEEDS REVIEW if any field is uncertain; else overall PASS. A clear violation is never masked by an unrelated unreadable field, and the tool never PASSES while anything is uncertain.
  - **Warning specific:** read clearly but not verbatim equals FAIL; partial / garbled / low confidence read equals NEEDS REVIEW. The agent can override any verdict (human in the loop).
  - The confidence cutoff is not guessed; it is calibrated against the eval label set (MVP13).
- [MVP9] **Match check pass.** Compare extracted fields against a mock application using field specific strictness: brand name compared after case and punctuation normalization (so "STONE'S THROW" matches "Stone's Throw"); the government warning compared exactly. The mock application JSON is modeled on TTB Form 5100.31 fields (brand, class/type, alcohol content, net contents, name and address), documented as a stand in, not invented. The UI exposes an optional application data panel (paste or upload JSON; blank runs compliance only), and the app ships two or three pre paired examples including one deliberate mismatch (label 45% ABV vs application 40%) and one normalized brand match. Results show two separate blocks: "Label vs Law" (compliance) and "Label vs Application" (match), never conflated.
- [MVP10] **Clean UI with a simple selection landing step.** A landing step asks one obvious question (which beverage type), with distilled spirits active and wine and beer shown as coming soon; it orients the user and primes the model client on arrival. Then an upload screen, then a result screen a non technical agent reads at a glance: big overall verdict, color coded per field rows, the uploaded image alongside, and the measured processing time (for example "verified in 2.3s"). Dead simple throughout, no hunting for buttons.
- [MVP11] **Honest error handling.** Unreadable image or low extraction confidence returns "request a better image" or routes the field to human review. The tool never auto passes a field it could not read.
- [MVP12] **Public deployment.** A working prototype reachable at a public URL for the reviewers to test.
- [MVP13] **Eval and unit tests.** Two layer testing.
  - **Rule engine (no image, no model):** pure functions tested by feeding field dictionaries with known values and asserting the verdict. Fast, deterministic, where rule correctness is proven.
  - **Controlled label set (known ground truth):** labels rendered from data we control (HTML/CSS or Pillow), so the correct verdict is known by construction. One compliant baseline plus single mutation variants (title case warning, 800 mL fill, dropped sentence, proof without percent). Each ships a manifest (fields + expected verdict + expected failing rule) that drives parametrized pytest cases. AI image generation may supply non text visual flavor only; regulated text is always injected by us.
  - **Real bottle photos:** authentic labels photographed (glare, angles, curved glass) used as PASS cases and to exercise extraction and the NEEDS REVIEW path. Ground truth set by a human reading the actual label.
  - The live model is mocked in CI for determinism; a small manual pass runs real photos through the live model. The confidence cutoff is calibrated against this set.

## Final Submission Features

Stretch items, pursued only after the distilled spirits path works end to end. These are documented as TODOs in `presearch.md`.

**Coverage**
- Wine rules (sulfite declaration at 10 ppm, table wine alcohol exception) per 27 CFR Part 4.
- Malt beverage / beer rules (alcohol content optional and State gated, "ABV" abbreviation not permitted) per 27 CFR Part 7.

**Throughput**
- Batch upload of 200 to 300 labels with a results table. Single label path is architected so batch is a thin wrapper.

**Input formats (production path: input aware rigor)**
- Accept true vector PDF artwork in addition to images. A vector PDF carries real type sizes in points, font weight, and element positions, so the Tier 2 warning checks (type size in mm, bold, contrasting background, separate and apart) can be promoted from advisory to hard pass/fail for that input type. Images stay Tier 1 only because pixels carry no physical scale. The extractor is architected so a PDF branch can slot in. Documented in the README as the production path; built only after the image MVP is complete.

**Robustness and polish**
- Image preprocessing assistance for skewed, glare heavy, or poorly lit photos.
- Soft advisory "horizon" flags for proposed rules (allergen, Alcohol Facts nutrition, cancer warning) presented as informational only, never as pass/fail gates.
- Exportable audit trail of each verdict and its reasoning.

## Performance Targets

| Metric | Target |
| --- | --- |
| Per label latency (warm, p95) | Under 5 seconds, measured and shown on the result page. "Warm" and p95 because the constraint that lost the prior vendor was the occasional slow label, not the average. |
| Vision extraction | One Claude vision call per label. Never chain calls. |
| Rule engine evaluation | Under 50 ms (pure functions, no I/O) |
| Cold start on demo host | Eliminated for reviewers via an always-on tier (container never idles down). The selection landing step also primes the model client on arrival. |
| Eval suite pass rate | 100 percent of known verdicts reproduced before delivery |

## Scope Boundaries

**In scope**
- Distilled spirits, single label, compliance check plus match check.
- Cloud Claude vision for extraction.
- Public demo deployment and README.

**Out of scope**
- Direct integration with the COLA system (explicitly excluded by IT).
- Wine and beer rule sets for the MVP (post MVP TODO).
- Batch upload for the MVP (post MVP TODO).
- Persistent storage of any sensitive or applicant data.
- Authentication, user accounts, role management.
- Production grade security hardening and self hosted inference (documented as the production migration path, not built now).
