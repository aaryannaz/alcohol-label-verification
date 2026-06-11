# Alcohol Label Verification

**Deployed:** https://alcohol-label-verification-fawn.vercel.app

## Approach

TTB reviewers currently compare physical label artwork against approved COLA applications by eye. This prototype automates that comparison:

1. The reviewer uploads label artwork as one combined file or as separate front/back files.
2. Gemini Vision extracts all regulated fields from the artwork into structured JSON.
3. Extracted fields populate both the Expected COLA and Reviewed Label columns simultaneously.
4. The reviewer corrects the Expected COLA side to match their COLA application if needed.
5. Clicking Verify compares both sides field-by-field and flags mismatches.

This eliminates manual data entry for the common case where the label artwork closely matches the COLA, reducing reviewer effort to correction and confirmation rather than transcription.

## Tools

- **FastAPI** — API and static file serving
- **Gemini Vision (gemini-2.5-flash, "thinking" disabled)** — label field extraction from images (set in `backend/app/clients.py`; override with the `GEMINI_MODEL` env var). Thinking is turned off because reading a label is a perception task, not a reasoning one — this keeps extraction at ~2s (under the ~5s stakeholder bar) while remaining accurate.
- **Vercel** — deployment
- **Python 3.12**

## Assumptions

- Label artwork is provided as an image (PNG, JPEG, WebP) or PDF up to 10 MB.
- A single uploaded file may contain all label panels needed for one review item.
- The reviewer has access to the approved COLA application to verify the expected fields.
- Government warning text must match the exact statutory wording, in all caps, with the heading "GOVERNMENT WARNING:".
- Vintage years, beer styles, and origin descriptors (e.g. "Imported") are not treated as fanciful names or class/type designations.

## Regulated fields checked

Beyond brand name, class/type, alcohol content, net contents, the government
warning, name/address, country of origin, sulfite declaration, and fanciful
name, the tool extracts and validates the conditional disclosures the TTB
checklists call out, scoped to the applicable product category:

- **Additive disclosures** (all categories, conditional): FD&C Yellow #5 (27 CFR 7.63(b)(1)/4.32(c)/5.63(c)(5)), Cochineal/Carmine (7.63(b)(2)/4.32(d)/5.63(c)(6)), and Aspartame "PHENYLKETONURICS: CONTAINS PHENYLALANINE." with an all-caps format check (malt only, 7.63(b)(4)).
- **Distilled spirits**: statement of age (5.74), commodity/neutral-spirits statement (5.71), coloring materials (5.63(c)(6)), wood treatment (5.73), state of distillation (5.66(f)).
- **Wine**: vintage date, grape varietal, percentage of foreign wine (4.32(a)(4)), the appellation-of-origin trigger (mandatory when a varietal/vintage/semi-generic type/"estate bottled" is present — 4.25/4.34), and the table-wine ABV exemption (a "table wine"/"light wine" may omit a numeric ABV — 4.36(a)).

A conditional field present on the label but blank in the Expected COLA is
flagged for the reviewer to confirm rather than silently passed.

The verification response also carries label-only **compliance checks** (shown
under the results table): net-contents unit system (metric for wine/spirits,
U.S. customary for malt — 27 CFR 4.37/5.70/7.70), standard of fill for wine and
spirits (27 CFR 4.72/5.203, advisory — verify the size tables against the
current regulation), origin coherence (populated fields vs the selected origin),
and the distilled-spirits state-of-distillation vs name/address consistency.

## Limitations

Because extraction is text-only (no typography, type-size, or panel/location
metadata), the following checks are **not machine-verifiable** and remain a
reviewer's visual judgment — the tool does not assert them:

- **Typography & placement:** bold of "GOVERNMENT WARNING", minimum type size by container (27 CFR 16.22), "separate and apart" placement, and the distilled-spirits "same field of vision" requirement (brand + ABV + class/type on one panel, 5.63).
- **Whether a conditional disclosure actually applies:** additive/sulfite disclosures are mandatory only if the additive is used — a formulation fact on the COLA/formula, not the label image. The tool surfaces whether the statement appears; the reviewer confirms applicability.
- **Standard-of-fill currency:** the approved-fill checks for wine/spirits are advisory — the size tables (27 CFR 4.72/5.203) change by regulation, so a "not approved" result flags the size for the reviewer to confirm against the current CFR rather than asserting a hard violation. Wine standard-of-fill exceptions (e.g. 27 CFR 4.70(b)) are not modeled.
- **Verbatim alcohol-content statement format:** whether the ABV statement's abbreviations are acceptable, and (spirits) whether a proof statement is "adequately distinguished" from the ABV, are not checked (the latter is a typographic/placement judgment, not text-verifiable).
- **Handwritten or low-quality labels:** extraction accuracy depends on image quality.
- **COLA document upload:** the Expected COLA side is pre-filled from the label artwork and corrected manually; a future improvement would extract fields from an uploaded COLA PDF.
- **Batch import:** batch mode supports multiple label files in one browser session; CSV/Excel mapping to expected COLA fields is a future enhancement.

## Extraction accuracy

An eval harness (`backend/evals/`) measures field-extraction accuracy against a
labeled set of synthetic label cases. Run it with
`cd backend && venv/bin/python -m evals.run_eval`. Extraction is **category-aware**:
the response schema is scoped to the fields applicable to the selected product
category, which keeps the model focused and avoids the accuracy loss of asking
for every field at once.

## Project Layout

```text
requirements.txt     Runtime dependencies (the file Vercel installs)
pyproject.toml       Packaging metadata + ruff (lint) config
vercel.json          Vercel build / routing config
.python-version      Python version (3.12)
.github/workflows/   CI: ruff + tests on every push / PR
backend/
  app/
    main.py          FastAPI app: routes, exception handlers, middleware
    fields.py        Canonical regulated-field list (single source of truth)
    schemas.py       Pydantic request models + product/origin enums
    clients.py       Gemini client + model / timeout config
    extraction.py    Image -> JSON field extraction (Gemini, category-aware)
    prompts.py       The extraction prompt (most domain rules live here)
    validation.py    Rule-based field comparison + TTB compliance logic
    uploads.py       Upload validation (extension / content-type / signature)
    security.py      Rate limiting, optional auth, security headers, body cap
    observability.py Structured logging + per-request correlation IDs
    errors.py        AppError + one JSON error envelope for all failures
    static/          Browser UI (vanilla HTML/CSS/JS) served by FastAPI
  evals/             Extraction-accuracy eval harness (render, score, cases)
  tests/             Unit + API tests (test_validation.py, test_api.py)
  scripts/           gemini_smoke_test.py (Gemini connectivity check)
  main_gemini.py     Compatibility entrypoint (re-exports the app)
  requirements.txt   Mirror of the root file (for the backend/ workflow)
```

## Setup

Create a local environment file:

```bash
cp backend/.env.example backend/.env
```

Then edit `backend/.env` and set `GEMINI_API_KEY` — get a free key from
[Google AI Studio](https://aistudio.google.com/apikey). (The app starts without
one, but extraction will return a `MISSING_GEMINI_API_KEY` error and `/readyz`
will report not-ready until a key is set.)

Install dependencies:

```bash
cd backend
python -m venv venv
venv/bin/python -m pip install -r requirements.txt
```

## Run

From the project root:

```bash
backend/venv/bin/python -m uvicorn backend.app.main:app --reload
```

From `backend/`:

```bash
venv/bin/python -m uvicorn app.main:app --reload
```

The older entrypoint still works:

```bash
backend/venv/bin/python -m uvicorn backend.main_gemini:app --reload
```

Open the prototype UI at:

```text
http://localhost:8000/
```

Swagger remains available at:

```text
http://localhost:8000/docs
```

## Test

```bash
cd backend
venv/bin/python -m unittest discover tests
```

## Lint & CI

Lint with [ruff](https://docs.astral.sh/ruff/) (a `dev` extra in `pyproject.toml`):

```bash
backend/venv/bin/python -m pip install -e ".[dev]"   # or: pip install ruff
ruff check backend/app backend/tests backend/scripts backend/evals
```

`.github/workflows/ci.yml` runs ruff and the test suite on every push/PR, and
checks that the root and `backend/` `requirements.txt` stay in sync (the root one
is what Vercel installs; keep `pyproject.toml` aligned too).

## Logging & observability

Logging is configured at startup on the `app` namespace; set `LOG_LEVEL`
(default `INFO`). Every request gets a correlation id — propagated from an
inbound `X-Request-ID` or generated — that is attached to log records (including
the Gemini call timing), returned in the `X-Request-ID` response header, and
included in error responses as `error.request_id`, so a reported failure maps to
a server log line.

## UI

The minimal UI is served by FastAPI from `backend/app/static/`. It supports:

- Product category and origin toggles.
- Front/back label uploads.
- Upload mode selector for Choose File, Drag & Drop, and Batch workflows.
- Batch upload queue for multiple one-file review items.
- Dynamic required, conditional, and optional field lists (scoped to the product category).
- Reviewed-field verification without re-running extraction, with a results summary and per-field status badges (failing rows highlighted; the government warning is read-only on the Expected side since it is checked against the statutory text).
- **Export to CSV and print** of a verification result (with a print stylesheet) so the review can be attached to a case file; label compliance checks are included.
- **Accessibility/feedback:** status and errors are announced to assistive tech (`role="status"`/`aria-live`, `role="alert"`), a busy spinner shows during the slow Gemini call, and the category/origin and action controls are locked while a request is in flight (preventing a field-stack race). Client-side file-type/size validation before upload.
- Light/dark mode with local browser preference storage.
- Feedback link that opens a GitHub issue for tester notes.

## API

- `GET /fields` returns the canonical field set (key, label, control, applicable categories) — the single source of truth the UI loads.
- `GET /field-requirements` returns required, conditional, and optional fields for a `product_category` and `origin_type` (scoped to the category).
- `POST /extract` extracts label fields from uploaded artwork (category-aware response schema).
- `POST /verify-reviewed` validates reviewed/corrected fields plus the label-only compliance checks, without making another Gemini call.
- `GET /health` liveness; `GET /readyz` readiness (verifies the API key is configured, returns the model id; 503 if not ready).

Upload endpoints accept PDF, PNG, JPEG, and WebP files up to 10 MB each. Upload validation checks the file extension, browser-provided content type, and file signature before sending anything to Gemini.

**One error contract.** Every failure — application errors, request-validation (422), HTTP errors (404/405), and unexpected 500s — returns the same envelope (internal details are logged server-side, never leaked):

```json
{
  "error": {
    "code": "GEMINI_INVALID_JSON",
    "message": "Gemini returned a response that could not be parsed as JSON.",
    "details": {}
  }
}
```

The browser client wraps `/extract` and `/verify-reviewed` in an abort-on-timeout so the UI surfaces a clean "request timed out" message instead of hanging.

## Security

The API is open by default for the demo but ships the controls to lock it down
(all configurable via environment variables — see `backend/.env.example`):

- **Rate limiting:** the cost-bearing endpoints (`/extract`, `/verify-reviewed`) are rate-limited per client IP (`RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS`) to blunt cost-amplification abuse. The limiter is in-memory and single-instance; back it with a shared store (e.g. Redis) for a multi-instance deployment.
- **Optional bearer auth:** set `APP_API_TOKEN` to require `Authorization: Bearer <token>` on the cost-bearing endpoints.
- **Security headers:** every response carries a Content-Security-Policy (`default-src 'self'`, no inline scripts — the theme bootstrap is an external file), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and `Referrer-Policy: no-referrer`.
- **Docs gating:** set `ENABLE_DOCS=false` to disable Swagger/OpenAPI in production.
- **CORS:** same-origin only unless `CORS_ALLOW_ORIGINS` is set.
- **Body size:** a global `MAX_REQUEST_BYTES` cap (default 25 MB) plus the per-file 10 MB upload cap; error responses never echo raw model output.

Accepted residual risks (low, given uploaded bytes are only forwarded to Gemini and never decoded or executed locally): the magic-byte upload check is prefix-only (a polyglot could pass it), and PDFs are not parsed for page count / decompression bombs (bounded only by the 10 MB cap).

## Vercel Deployment

The repo is prepared for Vercel with:

- `vercel.json` using the `@vercel/python` builder against `backend/app/main.py`, with `config.includeFiles` so the `static/` UI assets ship in the function bundle.
- A repository-root `requirements.txt` — the location the `@vercel/python` builder reads to install runtime dependencies. (`pyproject.toml` is for local/editable installs; `backend/requirements.txt` is for the local `backend/` workflow. Keep the three in sync.)
- `.python-version` set to Python 3.12.
- `.vercelignore` to keep local environments, caches, tests, and scripts out of the deployment bundle.

Recommended deployment steps:

1. Push this repository to GitHub.
2. Import the repository in Vercel.
3. Set the Vercel project root to the repository root.
4. Add `GEMINI_API_KEY` as a Vercel environment variable.
5. Deploy.

For local Vercel testing, install the Vercel CLI and run:

```bash
vercel dev
```

## Notes

- The UI is intentionally minimal and served from the FastAPI app to keep the prototype deployable on a short timeline.
- Gemini is used for image extraction.
- Validation logic is separated so category-specific compliance rules can be expanded without touching the API layer.
- Malt beverage, distilled spirits, and wine now use separate validation paths.
- Government warning validation checks exact wording, punctuation, and capitalization while allowing OCR line-break differences. Bold type is a known limitation because the current extraction returns text, not typography metadata.
