# Error and Fix Log

Running log of build, runtime, API, and deployment errors and how they were resolved. Log anything that took more than five minutes to diagnose, plus all build, runtime, API, and deployment failures. Do not log typos, linter warnings, or expected test failures.

## Template

```
### YYYY-MM-DD: short title
- Error: the message or symptom
- Context: what was being attempted
- Root cause: the actual underlying reason
- Fix: what resolved it
- Prevention: how to avoid it next time
```

## Log

### 2026-06-07: Jinja2 crash on template render (Starlette signature change)
- Error: `TypeError: cannot use 'tuple' as a dict key (unhashable type: 'dict')` from jinja2 LRUCache when rendering any template; all template routes failed, only `/healthz` passed.
- Context: First pytest run of the app shell on Python 3.14 with Starlette 1.2.1.
- Root cause: The installed Starlette changed `TemplateResponse` to the request-first signature `TemplateResponse(request, name, context)`. The old `TemplateResponse(name, {"request": request, ...})` form caused Starlette to treat the context dict as the template name, so Jinja2 tried to use a dict as a cache key.
- Fix: Updated all five `templates.TemplateResponse(...)` calls in `app/main.py` to the request-first signature and removed `request` from the context dicts.
- Prevention: On current Starlette, always pass `request` as the first positional argument to `TemplateResponse`. Pinning versions (pip freeze) will keep this stable across machines.

## Common Issues to Watch For

**Anthropic / Claude vision**
- Forgetting to base64 encode the image or sending the wrong media type; the API rejects the message.
- Not using tool-use / a forced schema, so the model returns prose that breaks JSON parsing. Always force structured output.
- Using a model id that is not vision capable, or a slow tier that blows the 5 second budget. Confirm the id via the claude-api reference.
- Missing or unset `ANTHROPIC_API_KEY` in the host environment after deploy.

**FastAPI / uploads**
- `python-multipart` not installed, so form uploads fail with an unhelpful error.
- Large images causing slow requests or memory spikes; validate size with Pillow before the model call.
- Returning a dict where an `HTMLResponse` / template render is expected, so the page shows raw JSON.

**Rule engine**
- Over normalizing the warning text (lowercasing or stripping punctuation) and masking a real violation. Normalize whitespace only.
- Hard coding a stale standards of fill list; the authorized sizes were amended in 2020 and again in January 2025 (T.D. TTB-200). Keep the list sourced and dated.
- Treating proof as the alcohol statement; percent alcohol by volume is the mandatory field, proof is optional.

**Render / deployment**
- Serverless style cold starts adding seconds to the first request; this is why a persistent web service was chosen.
- Secrets committed by accident; `.env` must stay in `.gitignore`.
- Build failing because `requirements.txt` is incomplete or pinned to incompatible versions.
