# Approach, Tools & Assumptions

A short design writeup for the AI-Powered Alcohol Label Verification prototype.
(See the [README](../README.md) for setup/run instructions and the full feature list.)

## What it does

It automates what a TTB reviewer does by hand on a COLA application: read the
regulated fields off the label artwork, compare them to the approved
application, and flag anything that doesn't match — fast enough to actually use
(the interview notes set a ~5-second bar per label).

## Approach

**Two-stage pipeline, deliberately decoupled.**
1. **Extraction** — Gemini Vision reads the uploaded label image(s) and returns
   the regulated fields as structured JSON. Almost all "how to read a label"
   knowledge lives in the prompt, not the code.
2. **Validation** — a pure, rule-based, no-I/O comparison of the fields against
   the expected values. This is where the TTB rules live (required vs.
   conditional fields per product category, ABV tolerance, net-contents units
   and standards of fill, the government-warning text, additive disclosures,
   wine appellation triggers, etc.). Because it's pure, it's deterministic,
   auditable, and the most heavily tested part of the system.

**One clean flow.** The reviewer uploads the label artwork; Gemini reads it,
the product category and origin are detected automatically (dropdowns default
to Auto and override a wrong guess), and a single editable column of
**COLA application fields** is pre-filled, turning transcription into
confirmation. The reviewer corrects any field so it reflects
the approved COLA application, then Verify compares application-says vs.
label-shows field-by-field — **without another AI call**, since validation is
pure. Re-verifying after an edit is instant. (Auto-reading the COLA application
form itself to pre-fill those expected values is a documented future improvement
— see below — left out because the brief calls for a standalone proof-of-concept,
not a COLA-system integration.)

**Category-aware extraction, auto-detected category.** The reviewer never picks
the product category or origin by hand: in auto mode the label is read with the
all-fields schema and both are inferred from the extracted text
(`app/classify.py` — deterministic and rule-based, no extra model call). When
the category is known (a reviewer override, or an explicit category passed to
the API), the response schema is scoped to the fields that apply to it (malt
beverage / wine / distilled spirits), keeping the model focused on a smaller
schema.

**Quality is measured, not assumed.** An eval harness renders ground-truth label
cases, runs them through the production extraction path (the same auto-detect
flow the app ships), and scores each field — currently 100% (418/418 fields
across 32 cases), with the category/origin classification scored and spurious
extractions flagged. Prompt and model changes are gated on it.

**Performance.** Extraction runs at ~2s by using `gemini-2.5-flash` with its
"thinking" phase disabled — reading a label is perception, not reasoning, so
thinking only added latency. Batch mode processes files **in parallel** (a small
worker pool), so a batch finishes in a fraction of the sequential time; the
brief's peak-season scenario — importers dumping 200–300 applications at once —
is what the per-IP rate limit is sized for, with the client pacing itself on
429 `Retry-After` signals. Each batch row gets an automatic
**Pass / Needs-attention** verdict from a single extract-and-validate call
(`POST /verify`), and separate front/back photos named alike with
`_front`/`_back` suffixes pair into one review item.

## Tools used

| Layer | Choice |
|---|---|
| Backend | **FastAPI** (Python 3.12), **Uvicorn**, **Pydantic** |
| AI | **Google Gemini Vision** (`gemini-2.5-flash`) via the `google-genai` SDK, with structured JSON output |
| Frontend | **Vanilla HTML/CSS/JS** — no framework or build step, served by FastAPI itself |
| Eval / tooling | **Pillow** (renders synthetic test labels), **ruff** (lint), **GitHub Actions** (CI: lint + tests) |
| Deployment | **Vercel** (`@vercel/python` serverless) |

The frontend is intentionally framework-light and served by the same FastAPI
app — one deployable unit, appropriate for a prototype on a short timeline.

## Key decisions & trade-offs

- **Decoupled extraction and validation** — Gemini reads the label, but the
  comparison itself is a separate, pure step. Re-verifying after the reviewer
  edits a field costs no AI call.
- **No AI in the verdict** — the pass/fail comparison is pure Python, so results
  are deterministic and explainable, not a black box.
- **Single source of truth for the field set** (`fields.py`): adding or renaming
  a regulated field is a one-line change that flows to the schema, validation,
  API, and UI.
- **`gemini-2.5-flash`, thinking off**: best balance — more accurate than
  `flash-lite` (which dropped hard fields like proprietary names) and far faster
  than `flash` with thinking on (~2s vs ~7s).

## Assumptions made

- Label artwork is provided as an image (PNG/JPEG/WebP) or PDF, ≤ 10 MB, and a
  single uploaded file may contain all panels for one review item.
- The reviewer has the approved COLA application on hand; the expected fields are
  pre-filled from the label extraction and the reviewer corrects them to the
  application's values. (Auto-reading the COLA form to fill those fields is a
  future improvement — see below.)
- The government warning must match the exact statutory wording; the
  "GOVERNMENT WARNING" heading must be capitalized, but the body's letter case is
  not regulated (all-caps is compliant). Bold, type size, and placement are
  **not** verifiable from extracted text and are left to the reviewer.
- Conditional disclosures (FD&C Yellow #5, cochineal/carmine, aspartame,
  sulfites) are mandatory only *if the additive is used* — a formulation fact on
  the COLA, not the label image — so the tool surfaces whether the statement
  appears and the reviewer confirms applicability.
- Standard-of-fill tables change by regulation, so a non-standard size fails
  the check with wording that directs the reviewer to confirm the size against
  the current CFR tables rather than treating the result as final.
- Batches scale toward the brief's 200–300-file peak-season dumps: files are
  processed in parallel, the client paces itself when rate-limited (honoring
  `Retry-After`), and there is no hard cap — a larger batch simply takes
  proportionally longer.
- Rate limiting is in-memory and single-instance; a multi-instance production
  deployment would back it with a shared store (e.g. Redis).

## Known limitations / future work

- **COLA two-document comparison.** Auto-read the approved COLA application form
  (TTB Form 5100.31, including COLA-public-registry exports) so Gemini fills the
  expected fields from the form's typed boxes — a true label-vs-application
  check, instead of the reviewer entering the application values by hand. Left
  out deliberately: the brief frames this as a standalone proof-of-concept, not a
  COLA-system integration. (The form doesn't carry the full label text — e.g. the
  government warning — so those fields would still come from the label.)
- **Image robustness** — handle labels shot at an angle, with glare, or in poor
  lighting (a reviewer pain point in the interviews) rather than assuming a clean image.
- Typography/placement rules (bold, minimum type size, distilled-spirits
  "same field of vision," "separate and apart") aren't machine-verifiable from
  text — documented rather than enforced.
- Batch results aren't yet persisted or exportable as a group; CSV/Excel mapping
  of expected COLA values is a future enhancement.
- Production auth (an SSO/gateway in front) and a shared-store rate limiter.
