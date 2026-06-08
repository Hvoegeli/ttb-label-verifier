# Presearch — Take-Home Project: TTB Alcohol Label Verification App

_Date: 2026-06-07_
_Stage: prototype (Treasury interview take-home)_
_Status: Phases 1-3 complete. Stack specifics pending /in-distribution._

## Context already established (before checklist)

A full regulatory diff was completed against ttb.gov and the eCFR:
- 27 CFR Part 5 (distilled spirits, revised 2022), Part 4 (wine), Part 7 (malt beverages, revised 2022), Part 16 (health warning).
- 2020 + 2025 standards-of-fill final rules (T.D. TTB-200, Jan 2025).
- 2025 PROPOSED allergen/nutrition/"Alcohol Facts" rules (NOT in force) and the Jan 2025 Surgeon General cancer-warning advisory (advisory only, NOT law).

Key reg facts that drive the build:
- Government Warning text is statutorily verbatim (27 CFR 16.21); only "GOVERNMENT WARNING:" is caps+bold (16.22); type size scales with container size.
- Net-contents size must be an authorized standard of fill (27 CFR 5.203 for spirits); 750 mL is valid.
- Distilled-spirits ABV is mandatory as "% Alc/Vol"; proof is optional and may appear in parentheses (5.65).
- Class/type is rule-bound, not free text (5.141-5.143); "Kentucky Straight Bourbon Whiskey" is valid.
- Same-field-of-vision rule: brand + class/type + ABV must be co-located (5.63(a)).
- Allergen/nutrition/cancer-warning = proposed/advisory only -> soft "horizon" flags, never hard pass/fail gates.

## Phase 1: Constraints

### 1. Domain Selection
- **Domain:** Custom — U.S. federal regulatory compliance (TTB alcohol beverage labels).
- **Use cases:** Upload a label image -> extract the regulated fields -> validate against in-force TTB rules -> return PASS/FAIL with per-field reasons. Optional second pass: match extracted fields against a mock application form (the "data entry verification" the agents do today).
- **Verification requirements:** Government Warning verbatim + formatting (16.21/16.22); net contents = legal standard of fill (5.203); ABV format valid (5.65); class/type is a real designation (5.143).
- **Data sources:** Reg rules encoded from the eCFR (no live API call). AI-generated test label images.

### 2. Scale & Performance
- **Volume:** Prototype-level (low). Batch upload of 200-300 labels is a wishlist item, not core.
- **Latency:** HARD 5-second target per label — prior vendor died at 30-40s and lost all adoption.
- **Concurrency:** Demo-level only.
- **Cost:** Negligible at prototype volume.

### 3. Reliability Requirements
- **Cost of a wrong answer:** Asymmetric — a FALSE PASS (waving through a non-compliant label) is worse than a false fail. Tool leans toward flag-for-human-review; never auto-approves.
- **Non-negotiable verification:** The Government Warning verbatim check (statutory, exact).
- **Human-in-the-loop:** YES, always. This is an assistant to the 47 agents, not a replacement.
- **Audit/compliance:** Deterministic rule engine = auditable by construction (every verdict traces to a CFR citation). LOCKED: project gets a real audit gate before final delivery — /correct + /security-review (file-upload attack surface) + /ship-check.

### 4. Team & Skill Constraints
- **Team:** Harrison (early-career programmer) + Claude.
- **Frameworks:** No agent framework (LangChain/LangGraph/CrewAI). This is a deterministic pipeline, not an agent. Heavy framework would be out-of-distribution over-engineering and would hurt the "appropriate technical choices" + "code quality" rubric scores.
- **Hard parts:** Reg-rule encoding (mostly done via the diff) and clean image extraction — NOT orchestration.

## Phase 2: Architecture Discovery (IN PROGRESS)

### 5. Agent Framework Selection
- **Decision:** None. Single deterministic pipeline: image -> vision extraction (1 AI call) -> deterministic rule engine -> verdict. No agent loop, no tool-calling, no persisted state.

### 6. LLM Selection
- **Decision:** Cloud vision LLM (Claude) for the prototype — fast enough for the 5s budget, strong on skewed/glare images (Jenny's wish). DOCUMENTED: a production deployment behind TTB's firewall would swap to self-hosted/on-prem inference (their firewall blocks outbound cloud ML endpoints; the public prototype URL is not behind that firewall).
- _Stack specifics deferred to /in-distribution._

### 7. Tool Design
- Two internal steps, no external APIs. Vision extractor (Claude vision -> structured JSON of label fields) + rule engine (one small pure function per CFR rule). Mock application = a JSON object for the match-check pass.
- Per-step error handling: unreadable image -> "request a better image" (mirrors current agent behavior); low-confidence field -> flag, do not guess.

### 8. Observability Strategy
- Minimal: structured logs of each request's extracted fields + verdicts. No LangSmith/Braintrust (agent-tracing tooling; overkill for a one-shot pipeline). Cost tracking trivial.

### 9. Eval Approach
- LOCKED: build a hand-crafted test-label set (~15-25 images) with KNOWN correct verdicts. Mix of fully compliant + planted violations (title-case "Government Warning," illegal 800 mL fill, dropped warning sentence, "90 Proof" with no % Alc/Vol, etc.). Run pipeline, compare to ground truth.
- Triple duty: proves correctness, serves as the regression suite, doubles as the live demo. Automated.

### 10. Verification Design
- The claim that needs verifying is the EXTRACTION (vision can misread/hallucinate). Rule verdicts are deterministic code and need no "checking."
- Confidence-gate extraction: can't read confidently -> flag for human, never invent a value. Escalation: anything ambiguous -> human review, never auto-pass.

## Phase 3: Post-Stack Refinement (sanity pass)

- **11. Failure modes:** Unreadable image -> "request better image." Vision API down -> clean error, no crash. Ambiguous field -> human.
- **12. Security:** File upload is the real attack surface — validate type/size, don't persist sensitive data, API key in env/secrets (never in repo). PROMPT-INJECTION via label image text mitigated structurally: vision model only returns field values, it never decides PASS/FAIL (the deterministic rule engine does), so a hijacked extraction can't forge a verdict — worst case a mis-read field caught by confidence-gate + human review. Call this out in the README.
- **13. Testing:** Unit tests per rule function (deterministic = easy). One integration test over the full pipeline. The eval label-set IS the regression suite.
- **14. Open source:** GitHub repo, MIT license (likely), README is a required deliverable.
- **15. Deployment:** Public deployed URL required. Host chosen in /in-distribution.
- **16. Iteration:** Largely out-of-scope for a take-home; reviewers are the feedback loop.

## Decisions locked in

- **A. Scope:** Compliance-check (label vs. TTB law) is the SPINE; match-check (label vs. mock application) is a thin second pass reusing the same extracted fields. Build both, weighted to compliance.
- **B. Beverage scope:** Distilled spirits = the working end-to-end demo path (matches the sample label). Rule engine structured so wine (sulfites) and beer (ABV-optional) plug in. Add wine/beer only if time remains.
- **C. Extraction:** Cloud vision LLM now; documented offline/self-hosted path for production.
- **Firewall contradiction resolved:** prototype uses cloud (public URL, not behind their firewall); production note covers the on-prem swap.
- **No heavy agent framework** — deterministic pipeline in plain code.
- **AI for perception, deterministic code for judgment** — vision model reads the image; plain rule code decides compliance.
- **Audit gate before delivery** — /correct + /security-review + /ship-check.
- **Proposed rules (allergen/nutrition/cancer) are soft horizon flags, never hard gates.**
- **Eval/test-label set:** BUILD IT (~15-25 labels, known verdicts, planted violations) — proof of correctness + regression suite + demo.
- **Prompt-injection defense is structural:** vision extracts, deterministic rules decide.

## TODOs (post initial build)

- **Batch upload (200-300 labels):** NOT in core MVP. Architect the single-label path so batch is a thin wrapper (loop + results table). Build out fully only after the single-label distilled-spirits path works end-to-end.
- **Wine + beer rules:** add after distilled spirits is fully working, if time remains (wine sulfite declaration; beer ABV-optional/State-gated).

## Open questions / unresolved

- Stack specifics (language, web framework, hosting) — to be settled via /in-distribution.
