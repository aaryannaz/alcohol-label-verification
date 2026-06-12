# Alcohol Label Verification

**Deployed:** https://alcohol-label-verification-fawn.vercel.app

## Approach

TTB reviewers currently compare physical label artwork against approved COLA applications by eye. This prototype automates that comparison:

1. The reviewer uploads the label artwork (one combined file, or separate front/back files).
2. Gemini Vision reads the label, the product category and origin are auto-detected from the extracted text (override dropdowns default to Auto), and a single set of editable **COLA application fields** is pre-filled — turning transcription into confirmation.
3. The reviewer corrects any field so it reflects the approved COLA application.
4. Clicking Verify compares application-says vs. label-shows field-by-field and flags mismatches — with no further AI call, since validation is pure.

Auto-reading the COLA application form itself (Form 5100.31) to pre-fill the expected values is a natural next step — see [Limitations](#limitations). It's intentionally out of scope here: the brief frames this as a standalone proof-of-concept, not a COLA integration.

## Tools

- **FastAPI** — API and static file serving
- **Gemini Vision (gemini-2.5-flash, "thinking" disabled)** — label field extraction from images (set in `app/clients.py`; override with the `GEMINI_MODEL` env var). Thinking is turned off because reading a label is a perception task, not a reasoning one — this keeps extraction at ~2s (under the ~5s stakeholder bar) while remaining accurate.
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
current regulation), origin coherence (populated fields vs the resolved origin),
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
- **Batch import:** batch mode supports multiple label files in one browser session; CSV/Excel mapping to expected COLA fields is a future enhancement.

## Possible improvements

- **COLA two-document comparison.** Today the reviewer types/corrects the expected values, which represent the approved COLA application. A natural enhancement is to upload the COLA application form (TTB Form 5100.31, including COLA-public-registry exports) and have Gemini read its typed boxes to pre-fill those expected fields automatically — a true label-vs-application comparison. This was intentionally left out: the brief frames the prototype as a standalone proof-of-concept, not a COLA-system integration. (The form also doesn't carry the full label text — e.g. the government warning — so those fields would still come from the label.)
- **Image robustness.** Handle labels shot at an angle, with glare, or under poor lighting (a reviewer pain point in the interviews) rather than depending on a clean image.

## Extraction accuracy

An eval harness (`evals/`) measures field-extraction accuracy against a
labeled set of synthetic label cases. The harness renders its label artwork
with Pillow, which ships in the `dev` extra — install it first
(`venv/bin/python -m pip install -e ".[dev]"`, or `pip install pillow`), then
run `venv/bin/python -m evals.run_eval`. Extraction is **category-aware**:
when the product category is known, the response schema is scoped to the
fields applicable to it, which keeps the model focused and avoids the accuracy
loss of asking for every field at once; in auto mode the label is read with
the all-fields schema and the category is inferred from the result. Current
baseline: 100% (418/418 fields across 32 cases, classification and
spurious-field checks included), p95 latency ≈ 3.2s — under the 5s bar.

## Project Layout

```text
requirements.txt     Runtime dependencies (the file Vercel installs)
pyproject.toml       Packaging metadata + ruff (lint) config
vercel.json          Vercel build / routing config
.python-version      Python version (3.12)
.env.example         Copy to .env and set GEMINI_API_KEY
.github/workflows/   CI: ruff + tests (pushes to main, all PRs)
app/
  main.py            FastAPI app: routes, exception handlers, middleware
  fields.py          Canonical regulated-field list (single source of truth)
  schemas.py         Pydantic request models + product/origin enums
  clients.py         Gemini client + model / timeout config
  extraction.py      Image -> JSON field extraction (Gemini, category-aware)
  prompts.py         The extraction prompt (most domain rules live here)
  classify.py        Deterministic category/origin detection from extracted fields
  validation.py      Rule-based field comparison + TTB compliance logic
  uploads.py         Upload validation (extension / content-type / signature)
  security.py        Rate limiting, optional auth, security headers, body cap
  observability.py   Structured logging + per-request correlation IDs
  errors.py          AppError + one JSON error envelope for all failures
  static/            Browser UI (vanilla HTML/CSS/JS) served by FastAPI
evals/               Extraction-accuracy eval harness (render, score, cases)
tests/               Unit + API tests (test_validation, test_classify, test_api, test_platform)
scripts/             gemini_smoke_test.py (Gemini connectivity check)
docs/                Submission documents (Design-Document.md + .pdf, README.pdf)
reference/           Project brief + TTB labeling checklists (source of the compliance rules)
tools/               make_pdfs.py (regenerates the docs/ PDFs)
archive/             Historical eval run logs and candidate prompts
CLAUDE.md            Project instructions for Claude Code
```

## Setup

Create a local environment file:

```bash
cp .env.example .env
```

Then edit `.env` and set `GEMINI_API_KEY` — get a free key from
[Google AI Studio](https://aistudio.google.com/apikey). (The app starts without
one, but extraction will return a `MISSING_GEMINI_API_KEY` error and `/readyz`
will report not-ready until a key is set.)

Install dependencies:

```bash
python -m venv venv
venv/bin/python -m pip install -r requirements.txt
```

## Run

From the repository root:

```bash
venv/bin/python -m uvicorn app.main:app --reload
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
venv/bin/python -m unittest discover tests
```

## Lint & CI

Lint with [ruff](https://docs.astral.sh/ruff/) (the `dev` extra in `pyproject.toml`, which also installs Pillow for the eval harness):

```bash
venv/bin/python -m pip install -e ".[dev]"   # or: pip install ruff
venv/bin/ruff check app tests scripts evals
```

`.github/workflows/ci.yml` runs ruff and the test suite on pushes to main and
on every pull request. The
repository-root `requirements.txt` is what Vercel installs; keep `pyproject.toml`
aligned with it.

## Logging & observability

Logging is configured at startup on the `app` namespace; set `LOG_LEVEL`
(default `INFO`). Every request gets a correlation id — propagated from an
inbound `X-Request-ID` or generated — that is attached to log records (including
the Gemini call timing), returned in the `X-Request-ID` response header, and
included in error responses as `error.request_id`, so a reported failure maps to
a server log line.

## UI

The minimal UI is served by FastAPI from `app/static/`. It supports:

- Product category and origin are auto-detected from the label (`app/classify.py`); compact dropdowns default to Auto, show the detected values, and override the detection — re-scoping the field list and re-extracting — in both single and batch modes.
- Upload the label artwork; the COLA application fields auto-fill from the label extraction (and re-extract automatically if the reviewer overrides the detected category or origin) for the reviewer to correct.
- Single and batch upload modes (click-to-browse or drag & drop); in single mode, front and back panels can be uploaded as two separate files.
- Batch mode auto-extracts and verifies each file via `POST /verify`, showing a per-row **Pass / Needs-attention** verdict; separate front and back images named alike with `_front`/`_back` suffixes (e.g. `airlie_front.jpg` / `airlie_back.jpg`) pair into one review item.
- Dynamic required, conditional, and optional field lists (scoped to the product category), ordered to match the COLA application form.
- Field-by-field verification with a results summary and per-field status badges (failing rows highlighted), plus label-only compliance checks. Re-verifying after the reviewer edits a field makes no additional Gemini call. The government warning is checked against the exact statutory text on both the expected and the label side.
- **Accessibility:** status and errors are announced to assistive tech (`role="status"`/`aria-live`, `role="alert"`), a busy spinner shows during the Gemini call, and the category/origin and action controls are locked while a request is in flight (preventing a field-stack race). Client-side file-type/size validation before upload.
- Light/dark mode (government-style layout throughout), with local browser preference storage.

## API

- `GET /fields` returns the canonical field set (key, label, control, applicable categories) — the single source of truth the UI loads.
- `GET /field-requirements` returns required, conditional, and optional fields for a `product_category` and `origin_type` (scoped to the category).
- `POST /extract` extracts label fields from uploaded artwork. `product_category` and `origin_type` default to `auto`: the label is read with the all-fields schema and both are inferred from the result; a known category scopes the response schema to its fields.
- `POST /verify` extracts and validates an uploaded label in one Gemini call, with the same `auto` category/origin detection (used by batch mode to give each row a Pass / Needs-attention verdict).
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

The browser client wraps `/extract`, `/verify`, and `/verify-reviewed` in an abort-on-timeout so the UI surfaces a clean "request timed out" message instead of hanging.

## Security

The API is open by default for the demo but ships the controls to lock it down
(all configurable via environment variables — see `.env.example`):

- **Rate limiting:** the cost-bearing endpoints (`/extract`, `/verify`, `/verify-reviewed`) are rate-limited per client IP (`RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS`) to blunt cost-amplification abuse. The limiter is in-memory and single-instance; back it with a shared store (e.g. Redis) for a multi-instance deployment.
- **Optional bearer auth:** set `APP_API_TOKEN` to require `Authorization: Bearer <token>` on the cost-bearing endpoints.
- **Security headers:** every response carries a Content-Security-Policy (`default-src 'self'`, no inline scripts — the theme bootstrap is an external file), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and `Referrer-Policy: no-referrer`.
- **Docs gating:** set `ENABLE_DOCS=false` to disable Swagger/OpenAPI in production.
- **CORS:** same-origin only unless `CORS_ALLOW_ORIGINS` is set.
- **Body size:** a global `MAX_REQUEST_BYTES` cap (default 25 MB) plus the per-file 10 MB upload cap; error responses never echo raw model output.

Accepted residual risks (low, given uploaded bytes are only forwarded to Gemini and never decoded or executed locally): the magic-byte upload check is prefix-only (a polyglot could pass it), and PDFs are not parsed for page count / decompression bombs (bounded only by the 10 MB cap).

## Vercel Deployment

The repo is prepared for Vercel with:

- `vercel.json` using the `@vercel/python` builder against `app/main.py`, with `config.includeFiles` so the `static/` UI assets ship in the function bundle.
- A repository-root `requirements.txt` — the location the `@vercel/python` builder reads to install runtime dependencies. (`pyproject.toml` is for local/editable installs; keep it in sync.)
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
