# Approach, Tools & Assumptions

A short design writeup for the AI-Powered Alcohol Label Verification prototype.
(See the [README](README.md) for setup/run instructions and the full feature list.)

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

**Expected-vs-Reviewed workflow.** One extraction pre-fills both an "Expected
COLA" column and a "Reviewed Label" column. The reviewer corrects the Expected
side to match their application, then Verify re-runs validation **without another
AI call**. This mirrors how a reviewer actually works (correct + confirm rather
than transcribe) and keeps the AI to one call per label.

**Category-aware extraction.** The response schema is scoped to the fields that
apply to the selected product category (malt beverage / wine / distilled
spirits), which both improves accuracy and cuts latency versus asking for every
field at once.

**Quality is measured, not assumed.** An eval harness renders ground-truth label
cases, runs them through the production extraction path, and scores each field —
currently ~99.5% accuracy. Prompt and model changes are gated on it.

**Performance.** Extraction runs at ~2s by using `gemini-2.5-flash` with its
"thinking" phase disabled — reading a label is perception, not reasoning, so
thinking only added latency. Batch mode processes up to 10 files **in parallel**
(a small worker pool), finishing a full batch in roughly the same ~10s budget.

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

- **One Gemini call per label** (pre-fills both columns) instead of a separate
  COLA-document upload: simpler, cheaper, faster. Documented as a simplification.
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
- There is no separate COLA upload yet — the Expected side is pre-filled from the
  artwork and corrected by the reviewer.
- The government warning must match the exact statutory wording; the
  "GOVERNMENT WARNING" heading must be capitalized, but the body's letter case is
  not regulated (all-caps is compliant). Bold, type size, and placement are
  **not** verifiable from extracted text and are left to the reviewer.
- Conditional disclosures (FD&C Yellow #5, cochineal/carmine, aspartame,
  sulfites) are mandatory only *if the additive is used* — a formulation fact on
  the COLA, not the label image — so the tool surfaces whether the statement
  appears and the reviewer confirms applicability.
- Standard-of-fill checks are advisory: the approved-size tables change by
  regulation, so a non-standard size is flagged for confirmation, not failed.
- Batch is capped at 10 files (15 was deemed overkill), processed in parallel to
  land near the ~10-second target.
- Rate limiting is in-memory and single-instance; a multi-instance production
  deployment would back it with a shared store (e.g. Redis).

## Known limitations / future work

- Separate COLA document upload (two-document flow) for divergent cases.
- Typography/placement rules (bold, minimum type size, distilled-spirits
  "same field of vision," "separate and apart") aren't machine-verifiable from
  text — documented rather than enforced.
- Batch results aren't yet persisted or exportable as a group; CSV/Excel mapping
  of expected COLA values is a future enhancement.
- Production auth (an SSO/gateway in front) and a shared-store rate limiter.
