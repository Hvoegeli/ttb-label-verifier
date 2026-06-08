# Testing Strategy

## Testing Pyramid

Weighted heavily toward fast unit tests, because the compliance logic is deterministic and that is where correctness lives.

- Unit tests: ~70 percent. Every rule function.
- Integration / eval tests: ~25 percent. The label set run through the pipeline against known verdicts.
- End to end: ~5 percent. A couple of FastAPI endpoint tests through the test client.

The vision model call is mocked in automated tests so the suite is deterministic and free to run. Real model behavior is exercised manually and through the eval label set during development.

## Coverage Targets

| Layer | Target | Tool |
| --- | --- | --- |
| Rule functions (`rules/`) | 100 percent of branches | pytest |
| Verdict assembler + matcher | 100 percent of outcomes (PASS / FAIL / NEEDS REVIEW, match / mismatch) | pytest |
| Extraction wrapper | Error and confidence paths covered (model mocked) | pytest |
| Endpoints | Happy path + bad upload + model error | pytest + httpx |

## Test Categories

**Rule unit tests.** Each rule gets a table of inputs and expected outcomes drawn straight from the regulations:
- Warning: exact pass; title case fail; missing sentence fail; altered wording fail; extra whitespace tolerated.
- Standards of fill: 750 mL pass; 800 mL fail; boundary sizes from 27 CFR 5.203.
- Alcohol content: "45% Alc./Vol." pass; "90 Proof" alone fail; proof alongside percent pass.
- Class/type: recognized designation pass; missing or unrecognized term fail or review.
- Presence: all mandatory fields pass; any missing fails with the named field.

**Eval tests (the label set).** Around 15 to 25 hand built label images, each paired with its known verdict, run through the full pipeline (model mocked or recorded). This is both the proof of correctness and the regression suite. Planted violations cover every FAIL reason the rules can emit.

**Matcher tests.** Brand normalization cases ("STONE'S THROW" vs "Stone's Throw"), exact warning comparison, and mismatch detection.

**Endpoint tests.** Upload a valid image (mocked extraction) and assert the result page renders the verdict; upload a bad file and assert a clean error; simulate a model error and assert no crash.

## CI Integration

- `pytest` runs the full suite locally and, if a CI pipeline is added, on every push.
- The model is always mocked in CI, so no API key or network is required and runs are deterministic.
- The eval suite must reproduce 100 percent of known verdicts before the project is considered deliverable.
- The audit gate (`/correct`, `/security-review`, `/ship-check`) runs before the final push, separate from the automated tests.

## Requirement Coverage Matrix

| Requirement | Covered by |
| --- | --- |
| [MVP1] image upload | endpoint test (valid upload) |
| [MVP2] field extraction | extractor tests (mocked model, confidence paths) |
| [MVP3] warning check | `rules/warning.py` unit tests + eval labels |
| [MVP4] standards of fill | `rules/fill.py` unit tests + eval labels |
| [MVP5] alcohol content format | `rules/abv.py` unit tests + eval labels |
| [MVP6] class/type | `rules/classtype.py` unit tests + eval labels |
| [MVP7] mandatory presence | `rules/presence.py` unit tests + eval labels |
| [MVP8] verdict assembly | assembler unit tests + eval labels |
| [MVP9] match check | matcher unit tests |
| [MVP10] result UI | endpoint test (result renders) |
| [MVP11] error handling | extractor confidence tests + endpoint error tests |
| [MVP12] deployment | manual public URL verification |
| [MVP13] eval and tests | the eval suite itself |
