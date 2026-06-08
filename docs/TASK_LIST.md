# Task List

Phased breakdown. Phase 1 is the MVP: a working single label distilled spirits path, deployed. Phase 2 is polish. Phase 3 is evaluation, the audit gate, and submission. Each group names the requirement it satisfies.

## Phase 1: MVP

### 1. Project setup [MVP12]
- [x] Initialize git repo, add `.gitignore` and `.env` template (plus committed `.env.example`)
- [x] Create `requirements.txt` with the locked dependencies
- [x] Scaffold FastAPI app with `/` (landing), `/upload`, `/verify`, `/healthz`
- [x] Confirm local run with Uvicorn

### 2. Image upload and UI shell [MVP1] [MVP10]
- [x] Beverage-selection landing page + upload page (Jinja2): single file input, submit button, short instructions
- [x] Image type and size validation with Pillow before any model call (normalize to JPEG, strip EXIF, downscale, HEIC support)
- [x] Result page skeleton: overall verdict banner, per field rows, uploaded image preview

### 3. Vision extraction [MVP2] [MVP11]
- [x] `extractor.py`: encode image, build the tool-use schema for label fields
- [x] One Claude vision call returning typed JSON (brand, class/type, alcohol content, net contents, name and address, warning text) with legibility flags
- [x] Confidence gate: not overall_legible routes to NEEDS REVIEW ("request a better image"); extraction errors do too
- [x] Confirm exact model id and params against the claude-api reference (default claude-haiku-4-5, $1/$5; Sonnet fallback via CLAUDE_MODEL)

### 4. Rule engine: distilled spirits [MVP3] [MVP4] [MVP5] [MVP6] [MVP7]
- [ ] `rules/warning.py`: verbatim Government Warning check (27 CFR 16.21) plus capitals on "GOVERNMENT WARNING:" (27 CFR 16.22); whitespace normalized only
- [ ] `rules/fill.py`: net contents against the authorized standards of fill list (27 CFR 5.203)
- [ ] `rules/abv.py`: percent alcohol by volume format accepted; proof optional and only alongside the percent (27 CFR 5.65)
- [ ] `rules/classtype.py`: class/type present and a recognized designation (27 CFR 5.141 to 5.143)
- [ ] `rules/presence.py`: all mandatory elements present (27 CFR 5.63)
- [ ] Each rule returns a structured outcome: status, plain reason, CFR citation

### 5. Verdict and match check [MVP8] [MVP9]
- [ ] Verdict assembler: combine rule outcomes into PASS / FAIL / NEEDS REVIEW with a per field breakdown
- [ ] `matcher.py`: compare fields to a mock application JSON; brand normalized, warning exact
- [ ] Wire verdict and match results into the result page

### 6. Deploy [MVP12]
- [ ] Render web service from the GitHub repo
- [ ] Set `ANTHROPIC_API_KEY` in host secrets
- [ ] Verify the public URL end to end and confirm latency under 5 seconds

## Phase 2: Polish

### 7. UX hardening [MVP10] [MVP11]
- [ ] Friendly error states (bad file, oversized, model timeout)
- [ ] Color coding and readable copy reviewed against the "73 year old" bar
- [ ] Loading indicator during the model call

### 8. Robustness
- [ ] Image preprocessing assistance for skew / glare / low light
- [ ] Soft advisory "horizon" flags for proposed rules (allergen, Alcohol Facts, cancer warning), clearly informational only

## Phase 3: Final

### 9. Eval and tests [MVP13]
- [ ] Build the test label set (~15 to 25 images) with known verdicts, including planted violations (title case warning, illegal fill size, dropped warning sentence, proof without percent)
- [ ] Unit tests per rule function
- [ ] Eval runner as parametrized pytest cases (image to expected verdict)
- [ ] Confirm 100 percent of known verdicts reproduce

### 10. Audit gate (before delivery)
- [ ] Run `/correct` on the full diff
- [ ] Run `/security-review` (file upload attack surface, secret handling)
- [ ] Run `/ship-check` before pushing

### 11. Submission
- [ ] README: setup, run, approach, tools, assumptions, trade offs, the cloud vs self hosted production note
- [ ] Final public URL confirmed live
- [ ] Repo pushed (feature branch first; main only on Harrison's say so)

## Post MVP TODOs (parked)
- Wine rules (27 CFR Part 4: sulfite declaration at 10 ppm, table wine alcohol exception)
- Beer rules (27 CFR Part 7: alcohol content optional / State gated, "ABV" abbreviation not permitted)
- Batch upload (200 to 300 labels) as a thin wrapper over the single label path
- Vector PDF input support: parse type size (points to mm), font weight, and element positions; promote the warning Tier 2 checks (type size, bold, contrasting background, separate and apart) from advisory to hard pass/fail on PDF input. Detect vector vs raster PDF; raster falls back to the image path.
