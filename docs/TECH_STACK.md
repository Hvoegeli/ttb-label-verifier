# Technology Stack

## Architecture Overview

A deterministic pipeline. The only AI step is reading the image. Every compliance decision is made by plain, testable code.

```
                    +-------------------------------+
   Browser          |        FastAPI app            |
  (agent)           |                               |
     |              |  1. /            upload form   |
     |  upload img  |  2. /verify      handler       |
     +------------->|        |                       |
                    |        v                       |
                    |  extractor.py                  |
                    |   one Claude vision call       |
                    |   (anthropic SDK, tool-use)    |
                    |        |                       |
                    |        v  fields as JSON        |
                    |  rules/ engine (pure funcs)    |
                    |   - warning   (27 CFR 16)      |
                    |   - fill      (27 CFR 5.203)   |
                    |   - abv       (27 CFR 5.65)    |
                    |   - classtype (27 CFR 5.143)   |
                    |   - presence  (27 CFR 5.63)    |
                    |        |                       |
                    |        v                       |
                    |  matcher.py (vs mock app JSON) |
                    |        |                       |
                    |        v                       |
   result page <----|  verdict (PASS/FAIL/REVIEW)    |
   (Jinja2)         |  + per-field reasons + cites   |
                    +-------------------------------+
```

No database. State lives only for the duration of one request.

## Stack Decisions

| Layer | Technology | Version | Rationale |
| --- | --- | --- | --- |
| Language | Python | 3.11+ | Most in distribution for the Anthropic SDK; the builder works fastest here. |
| Web framework | FastAPI | latest | Boring, widely used, excellent docs; trivial JSON and form handling. |
| ASGI server | Uvicorn | latest | Standard FastAPI server. |
| Templates | Jinja2 | latest | Server rendered HTML; one upload page, one result page. No SPA needed. |
| Frontend | HTML + vanilla JS | n/a | Dead simple UX bar. No build step, nothing to break. |
| Vision model | Anthropic Claude (vision) | confirm via claude-api skill | Strong on skewed / glare images; fast enough for the 5 second budget. Sonnet is the working default; Haiku if latency bound. |
| LLM SDK | anthropic (Python) | latest | Official SDK; tool-use forces structured JSON extraction. |
| Rule engine | Plain Python modules | n/a | Pure functions encoding 27 CFR Parts 5 and 16. Deterministic and auditable. |
| Tests | pytest | latest | Rule unit tests plus the eval label set as parametrized cases. |
| Hosting | Render (web service, cheapest always-on tier) | n/a | Deploys from GitHub. The always-on tier keeps the container running so reviewers never hit an idle spin-down cold start. Railway is the runner up. |
| Dependency mgmt | pip + requirements.txt | n/a | Simplest reproducible setup for a reviewer. |

## Key Dependencies

**Backend**
- `fastapi` — web framework and routing
- `uvicorn[standard]` — ASGI server
- `jinja2` — HTML templating
- `python-multipart` — file upload form parsing
- `anthropic` — Claude vision client
- `pydantic` — typed models for extracted fields and verdicts (ships with FastAPI)
- `pillow` — image validation, re-encode to JPEG, EXIF stripping, downscale
- `pillow-heif` — decode HEIC uploads (phone camera default) so they normalize to JPEG

**Dev / test**
- `pytest` — unit and eval test runner
- `httpx` — FastAPI test client for endpoint tests

**Frontend**
- None beyond plain HTML and vanilla JS served by FastAPI.

## Environment Variables

See `.env` for the template. Summary:

- `ANTHROPIC_API_KEY` — required. The Claude vision API key. Never committed.
- `CLAUDE_MODEL` — optional override for the vision model id (defaults to the Sonnet id confirmed via the claude-api reference at build time).
- `MAX_UPLOAD_MB` — optional. Reject images larger than this before calling the model.
- `APP_ENV` — optional. `dev` or `prod`; controls log verbosity.

## API Endpoints Summary

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/` | Serve the upload page. |
| POST | `/verify` | Accept an image (and optional mock application JSON), run the pipeline, render the result page. |
| GET | `/healthz` | Liveness check for the host. |

No database schema section: this prototype persists nothing.
