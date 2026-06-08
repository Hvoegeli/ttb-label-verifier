# Architecture Memo

## Project Summary

A web prototype that verifies distilled spirits labels against federal TTB rules. An agent uploads a label photo; one Claude vision call reads the regulated fields; a deterministic rule engine checks those fields against 27 CFR Parts 5 and 16 and returns a PASS / FAIL / NEEDS REVIEW verdict with a CFR citation for every line. Built for a Treasury take home; judged on correctness, code quality, appropriate technical choices, UX, and attention to requirements.

## Key Architecture Decisions

### 1. Deterministic pipeline, not an agent

We considered an agent framework (LangChain, LangGraph, CrewAI) and rejected it. Those tools exist to manage loops where an AI decides what to do next and carries state across steps. This app does the same fixed steps in the same order every time: read the image, then check the fields. There is no decision loop. Adding a framework would mean more dependencies, more failure points, slower responses against a hard 5 second budget, and harder to read code, which works directly against the "code quality" and "appropriate technical choices" rubric lines. We use plain Python instead.

### 2. AI for perception, plain code for judgment

The vision model has exactly one job: turn a messy photo into structured field values. Every compliance decision is made by deterministic rule functions. This split matters for three reasons. Reading a tilted, glare heavy bottle photo is genuinely hard, which is where the model earns its place. Deciding whether a federal warning is legally valid must be reproducible and inspectable, which a model's judgment is not. And it keeps the model out of the trust boundary: it never decides PASS or FAIL.

### 3. Compliance check as the spine, match check as a thin pass

The discovery interviews describe matching the label against the application (data entry verification). But "what TTB requires" actually lives in the regulations. So the primary build checks the label against the law, and the match against a mock application is a cheap second pass that reuses the already extracted fields. This answers both framings while leading with the harder, higher value one.

### 4. Field specific matching strictness

The interviews contain a deliberate tension: one agent wants fuzzy matching ("STONE'S THROW" equals "Stone's Throw"), another wants exact matching (the warning, word for word). The regulations resolve it. Brand name is a designation where case and punctuation do not change identity, so it is compared after normalization. The government warning text is fixed by statute, so it is compared byte for byte after normalizing whitespace only. Same app, two strictness levels, each justified by the rule it enforces.

### 5. Cloud vision now, self hosted later

IT noted their production network blocks outbound cloud ML endpoints. That constraint applies to their internal network, not to a public demo URL the reviewers open in a browser. So the prototype uses cloud Claude vision for speed and accuracy, and the README documents that a production deployment would swap to self hosted inference behind the firewall. This is recorded as a known production migration, not a gap.

### 6. Proposed rules are advisory, not gates

The 2025 allergen, Alcohol Facts nutrition, and cancer warning items are proposed or advisory only, not in force. Coding them as hard pass/fail gates would be factually wrong and would reject compliant labels. They are represented, if at all, as informational "horizon" notes.

### 7. Check only what the input can prove (input aware rigor)

A regulation can require a physical property the input cannot demonstrate. 27 CFR 16.22(b) sets the warning's minimum type size in millimeters (1 mm up to 237 mL, 2 mm up to 3 L, 3 mm above). Millimeters are a physical measurement; a photo is pixels with no inherent scale, and bottle volume does not fix bottle dimensions, so absolute size cannot be derived from an image. We therefore split the warning rule into Tier 1 (text content and capitals, which an image proves) as hard pass/fail, and Tier 2 (type size, bold, contrasting background, separate and apart) as advisory, displayed with the correct mm threshold for the detected container size but never an automated FAIL.

The production path is input aware: a true vector PDF carries real type sizes in points, font weight, and element positions, so on PDF input the Tier 2 checks are promoted to hard pass/fail. The MVP accepts images only (matching the brief, which supplies image labels); the PDF branch is architected for but deferred. This demonstrates understanding of both the regulation and the limits of the input, and avoids the false confidence of pretending to measure millimeters from a snapshot.

## Processing Strategy

1. Browser posts an image (and optionally a mock application JSON) to `/verify`.
2. `extractor.py` validates the image (type, size) and makes one Claude vision call using tool-use, which forces the model to return the fields as a typed JSON object with per field confidence.
3. The fields flow into the `rules/` engine: independent pure functions for the warning, standards of fill, alcohol content format, class/type, and mandatory field presence. Each returns a structured outcome with a reason and a CFR citation.
4. `matcher.py` compares the fields against the mock application using field specific strictness.
5. The verdict assembler combines rule outcomes and match results into one overall PASS / FAIL / NEEDS REVIEW plus a per field breakdown.
6. Jinja2 renders the result page beside the uploaded image.

## Known Failure Modes

| Failure | Mitigation |
| --- | --- |
| Unreadable or low confidence image | Return "request a better image" or route the field to human review. Never auto pass. |
| Vision model returns a malformed field set | tool-use schema validation rejects it; surface a clean error, not a crash. |
| Prompt injection text printed on the label | The model only returns field values; it never decides the verdict, so a hijacked extraction cannot forge a PASS. Worst case is a misread field caught by the confidence gate and human review. |
| Small print OCR misreads the warning and returns it confidently (false FAIL on a compliant label) | Always render a character level diff (label vs statute) so the agent verifies or overrides in one glance; the model is told to flag illegible portions, which route to NEEDS REVIEW. Documented limitation. |
| Vision API timeout or outage | Catch and show a friendly error; the rule engine is unaffected and independently testable. |
| Latency creeping past 5 seconds | Single model call, no chained calls; rule engine is sub 50 ms; choose a faster model tier if needed. |
| A label edge case the rules do not cover | Default toward NEEDS REVIEW rather than a false PASS, consistent with the asymmetric error cost. |
