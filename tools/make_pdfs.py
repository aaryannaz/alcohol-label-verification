"""Regenerate the submission PDFs (docs/README.pdf, docs/Design-Document.pdf).

Run from the repo root with its venv:
    cd alcohol-label-verification && venv/bin/python tools/make_pdfs.py

The PDFs are curated companions to README.md / docs/APPROACH.md — when those
change, update the content blocks below and re-run. Layout matches the
original submission PDFs (letter, Helvetica/Courier, page header).
"""

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer

GRAY = HexColor("#555555")
LIGHT = HexColor("#888888")

styles = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=20, leading=24, spaceAfter=2),
    "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=11.5, leading=15, textColor=GRAY, spaceAfter=4),
    "links": ParagraphStyle("links", fontName="Helvetica", fontSize=9.5, leading=13, textColor=GRAY, spaceAfter=10),
    "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=13, leading=16, spaceBefore=12, spaceAfter=5),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=13.5, spaceAfter=6),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=10, leading=13.5, leftIndent=10, spaceAfter=5),
    "mono": ParagraphStyle("mono", fontName="Courier", fontSize=8.3, leading=10.6, leftIndent=8, spaceBefore=2, spaceAfter=8),
}


def header(doc_name):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(LIGHT)
        canvas.drawString(0.85 * inch, 10.45 * inch, doc_name)
        canvas.drawRightString(letter[0] - 0.85 * inch, 10.45 * inch, f"Page {doc.page}")
        canvas.setStrokeColor(LIGHT)
        canvas.setLineWidth(0.5)
        canvas.line(0.85 * inch, 10.36 * inch, letter[0] - 0.85 * inch, 10.36 * inch)
        canvas.restoreState()

    return draw


def build(path, pdf_title, story):
    doc = SimpleDocTemplate(
        path,
        pagesize=letter,
        leftMargin=0.85 * inch,
        rightMargin=0.85 * inch,
        topMargin=0.95 * inch,
        bottomMargin=0.75 * inch,
        title=pdf_title,
        author="Aaryan Naz",
    )
    fn = header("Alcohol Label Verification")
    doc.build(story, onFirstPage=fn, onLaterPages=fn)
    print("wrote", path)


def P(text, style="body"):
    return Paragraph(text, styles[style])


def M(text):
    return Preformatted(text, styles["mono"])


LINKS = (
    'Live demo: https://alcohol-label-verification-fawn.vercel.app &nbsp;·&nbsp; '
    "Repository: github.com/aaryannaz/alcohol-label-verification"
)

# ---------------------------------------------------------------- README.pdf

readme = [
    P("Alcohol Label Verification", "title"),
    P("README — setup, structure, and how to run it locally", "subtitle"),
    P(LINKS, "links"),
    P("Summary", "h"),
    P(
        "A web app that automates what a TTB reviewer does by hand on a COLA (Certificate of Label "
        "Approval) application: it reads the regulated fields off the label artwork, compares them to the "
        "approved application, and flags anything that does not match. The reviewer uploads the label "
        "image(s); Google Gemini Vision reads them into structured fields, the product category and origin "
        "are detected automatically (dropdowns default to Auto and can override a wrong guess), and an "
        "editable set of COLA application fields is pre-filled; the reviewer corrects those to the approved "
        "application; a pure, rule-based engine then compares them field-by-field and runs the TTB "
        "compliance checks (required fields per beverage type, the exact government-warning text, additive "
        "disclosures, and more). Typical extraction is about 2 seconds; a batch mode processes many labels "
        "in parallel, each landing on a Pass / Needs-attention verdict."
    ),
    P(
        "<b>Backend:</b> FastAPI (Python 3.12). <b>AI:</b> Google Gemini Vision (gemini-2.5-flash). "
        "<b>Frontend:</b> vanilla HTML/CSS/JS served by the same app. <b>Deployed</b> on Vercel."
    ),
    P("File structure", "h"),
    M(
        """alcohol-label-verification/
  README.md  APPROACH.md  LICENSE        docs (this PDF mirrors README.md)
  requirements.txt                       runtime deps (installed by Vercel)
  pyproject.toml                         packaging + ruff (lint) config
  vercel.json   .vercelignore            deploy / routing config
  .python-version   .env.example         Python 3.12; copy to .env
  .github/workflows/ci.yml               CI: ruff + tests (main pushes, PRs)
  app/
    main.py            FastAPI app: routes, exception handlers, middleware
    fields.py          canonical regulated-field list (single source of truth)
    schemas.py         Pydantic request models + product / origin enums
    clients.py         Gemini client + model / timeout config
    extraction.py      image -> JSON field extraction (Gemini, category-aware)
    prompts.py         the extraction prompts (most domain rules live here)
    classify.py        deterministic category/origin detection (Auto mode)
    validation.py      rule-based field comparison + TTB compliance logic
    uploads.py         upload validation (extension / content-type / signature)
    security.py        rate limiting, optional auth, security headers, body cap
    observability.py   structured logging + per-request correlation IDs
    errors.py          one JSON error envelope for all failures
    static/            browser UI (HTML/CSS/JS) served by FastAPI
  evals/               extraction-accuracy harness (render, score, cases)
  tests/               unit + API tests (validation, classify, api, platform)
  scripts/             gemini_smoke_test.py (Gemini connectivity check)"""
    ),
    P("Run it locally (step by step)", "h"),
    P(
        "<b>1. Prerequisites.</b> Python 3.12 and a Google Gemini API key (free from Google AI Studio: "
        "aistudio.google.com/apikey)."
    ),
    P("<b>2. Get the code.</b>"),
    M(
        """git clone https://github.com/aaryannaz/alcohol-label-verification.git
cd alcohol-label-verification"""
    ),
    P("<b>3. Set your API key.</b> Copy the example env file and add your key."),
    M(
        """cp .env.example .env
# then edit .env and set GEMINI_API_KEY=your-key"""
    ),
    P("<b>4. Create a virtualenv and install dependencies.</b>"),
    M(
        """python -m venv venv
venv/bin/python -m pip install -r requirements.txt
venv/bin/python -m pip install -e ".[dev]"   # optional: ruff + Pillow (used by step 7)"""
    ),
    P("<b>5. Run the server</b> (from the repository root)."),
    M("venv/bin/python -m uvicorn app.main:app --reload"),
    P("<b>6. Open the app.</b> UI at http://localhost:8000/ &nbsp;·&nbsp; API docs at http://localhost:8000/docs"),
    P("<b>7. (Optional) Run the tests and the accuracy eval.</b>"),
    M(
        """venv/bin/python -m unittest discover tests          # unit + API tests (127)
venv/bin/python -m evals.run_eval                   # extraction accuracy + latency"""
    ),
]

# ------------------------------------------------------- Design-Document.pdf

design = [
    P("Alcohol Label Verification", "title"),
    P("Design Document — approach, implementation, and architecture decisions", "subtitle"),
    P(LINKS, "links"),
    P("1. Summary", "h"),
    P(
        "TTB reviewers process about 150,000 alcohol-label applications a year, and much of the work is "
        "rote matching: confirming the brand name, alcohol content, and government warning on the label "
        "match the approved application. This app automates that comparison. The reviewer uploads the "
        "label artwork; Gemini Vision reads it into structured fields, the beverage category and origin are "
        "detected automatically, and an editable set of COLA application fields is pre-filled, which the "
        "reviewer corrects to the approved application; a pure, rule-based engine compares them "
        "field-by-field and runs the TTB compliance checks. It returns in about 2 seconds per label, handles "
        "beer, wine, and distilled spirits, and offers a batch mode that verifies many labels in parallel. It is "
        "a standalone prototype deployed to a public URL, intentionally a single, simple deployable unit."
    ),
    M(
        """Upload label  ->  Gemini Vision: structured field JSON  ->  category/origin auto-detected
    ->  reviewer corrects  ->  pure rule engine: field comparison + TTB compliance checks
    ->  Pass / mismatch verdict per field, plus label-only advisory checks"""
    ),
    P("2. What the customers said they wanted", "h"),
    P("Drawn from the project brief and its discovery interviews:"),
    P(
        '<b>Speed above all.</b> A prior scanning-vendor pilot took 30-40 seconds per label and was abandoned: "if we '
        "can't get results back in about 5 seconds, nobody's going to use it\" (Sarah Chen, Deputy Director).",
        "bullet",
    ),
    P(
        "<b>The core task is matching.</b> Agents mostly confirm the value on the label equals the value on the "
        "application — brand name, ABV, government warning — which is exactly what should be automated.",
        "bullet",
    ),
    P(
        '<b>Judgment, not brittle matching.</b> "STONE\'S THROW" on the label vs "Stone\'s Throw" in the application '
        "is obviously the same product (Dave Morrison, 28-year agent). Cosmetic differences must not be flagged "
        "as mismatches.",
        "bullet",
    ),
    P(
        '<b>The government warning must be exact.</b> Word-for-word, with the "GOVERNMENT WARNING:" '
        "heading in all caps; a title-case heading is a real rejection reason (Jenny Park caught one).",
        "bullet",
    ),
    P(
        "<b>A dead-simple interface</b> for a workforce that is half over 50 and varies widely in tech comfort: "
        '"something my mother could figure out... clean, obvious, no hunting for buttons" '
        "(Sarah Chen — her benchmark user is her 73-year-old mother).",
        "bullet",
    ),
    P(
        "<b>Batch uploads.</b> Importers dump 200-300 applications at once during peak season, and today they are "
        "processed one at a time.",
        "bullet",
    ),
    P(
        "<b>Three beverage types</b> (beer, wine, distilled spirits) with type-specific required fields (the brief's "
        "TTB-requirements context); a standalone proof-of-concept, not integrated with the live COLA system, "
        "storing nothing sensitive (Marcus Williams, IT).",
        "bullet",
    ),
    P("3. How we implemented it", "h"),
    P(
        "<b>Two-stage pipeline.</b> Gemini extraction (image -> JSON) is decoupled from a pure, rule-based "
        "validation step. Because validation has no I/O, re-checking after the reviewer edits a field costs no "
        "additional AI call, and it is deterministic and fully unit-tested.",
        "bullet",
    ),
    P(
        '<b>Speed.</b> gemini-2.5-flash runs with its "thinking" phase disabled and returns in about 2s; an eval '
        "harness measures p50/p95 latency to keep it under the 5-second bar.",
        "bullet",
    ),
    P(
        "<b>Auto-detected category and origin.</b> The reviewer never picks the beverage type by hand: the product "
        "category and origin are inferred from the extracted text by a deterministic, rule-based classifier "
        "(app/classify.py — no extra model call). Dropdowns default to Auto, show what was detected, and can "
        "override a wrong guess, re-scoping the field list.",
        "bullet",
    ),
    P(
        "<b>Lenient-but-correct matching.</b> A normalize step ignores case, punctuation, and common "
        'abbreviations, so "STONE\'S THROW" matches "Stone\'s Throw" — exactly Dave\'s example — without '
        'passing genuine mismatches; unit-aware net-contents parsing treats "1 PINT 0.9 FL OZ" and "500 mL" '
        "as the same quantity.",
        "bullet",
    ),
    P(
        "<b>Government warning.</b> Checked against the exact statutory text on both the expected and the label "
        "side; the heading must be all caps, and a title-case heading returns a specific FAIL_HEADING_FORMAT "
        "verdict — the rejection Jenny described.",
        "bullet",
    ),
    P(
        "<b>Simple UI.</b> One clean editable column, an Instructions page, a red asterisk on required fields, and "
        "explicit empty / loading / error states — no hunting for buttons.",
        "bullet",
    ),
    P(
        "<b>Batch mode.</b> Files are verified in parallel and each row lands on an at-a-glance Pass / "
        "Needs-attention verdict from a single extract-and-validate call (POST /verify); the batch paces itself "
        "when rate-limited (honoring Retry-After), and separate front/back photos named with _front/_back "
        "suffixes pair into one review item.",
        "bullet",
    ),
    P(
        "<b>Beverage-aware.</b> The field set and the required / conditional / optional rules switch per product "
        "category, all driven from a single source of truth so the schema, validation, API, and UI never drift.",
        "bullet",
    ),
    P(
        "<b>Quality is measured, not assumed.</b> An eval harness renders ground-truth labels, runs the real "
        "production extraction path (including auto-detection), and scores every field — currently 100% "
        "(418/418 fields across 32 cases), with the category/origin classification scored and spurious "
        "extractions flagged. Prompt and model changes are gated on it.",
        "bullet",
    ),
    P(
        "<b>What the tool validates.</b> Coverage is scoped to the selected beverage type, so a beer is never asked "
        "for wine or spirits fields:"
    ),
    P(
        "<b>Common (all types):</b> brand name, class/type designation, alcohol content, net contents, name/address "
        "of the bottler or importer, country of origin for imports, and the government warning.",
        "bullet",
    ),
    P(
        "<b>Conditional disclosures:</b> FD&amp;C Yellow #5, cochineal/carmine, aspartame (with an all-caps format "
        "check), and sulfites — surfaced when present for the reviewer to confirm applicability.",
        "bullet",
    ),
    P(
        "<b>Wine:</b> grape varietal, the appellation-of-origin trigger, vintage date, and a table-wine "
        "alcohol-content exemption.",
        "bullet",
    ),
    P(
        "<b>Distilled spirits:</b> statement of age, commodity statement, coloring materials, wood treatment, and "
        "state of distillation.",
        "bullet",
    ),
    P("<b>Label-only advisory checks:</b> net-contents unit system, standard of fill, and origin coherence.", "bullet"),
    P("4. Why this architecture", "h"),
    P(
        "<b>AI model — Google Gemini Vision (gemini-2.5-flash, thinking disabled).</b> The task is to read text off "
        "a photograph and return structured data, so we need a vision model with enforced JSON-schema output — "
        'Gemini provides both. Reading a label is perception, not reasoning, so disabling the model\'s "thinking" '
        "phase cut latency from ~7s to ~2s with no measured accuracy loss — the single change that meets the "
        "5-second bar. We chose 2.5-flash over flash-lite (more accurate on judgment fields, e.g. telling a fanciful "
        "name from a class/type) and over flash-with-thinking (too slow).",
        "bullet",
    ),
    P(
        "<b>Backend — FastAPI (Python), not Flask.</b> Async request handling lets a batch fan out concurrent "
        "Gemini calls; Pydantic gives typed request validation and the field schema for free; OpenAPI/Swagger "
        "docs are automatic; and it serves the static UI itself, so the whole app is one deployable unit. Flask "
        "would need bolt-on extensions for each of those.",
        "bullet",
    ),
    P(
        "<b>Frontend — vanilla HTML/CSS/JS, not Next.js/React.</b> The UI is a few forms and a results table, not "
        "an application that needs a single-page framework. No build step, no node_modules, no hydration — just "
        'static files served by the same backend. Fewer moving parts directly serves the "clean, obvious" mandate '
        "and keeps the deploy a single artifact.",
        "bullet",
    ),
    P(
        "<b>Hosting — Vercel.</b> Zero-config serverless Python, deploy-on-git-push, and a generous free tier — "
        "ideal for a prototype that needs a public URL reviewers can test, with fast iteration.",
        "bullet",
    ),
    P(
        "<b>Honest trade-offs (prototype vs production).</b> (a) IT noted TTB's network blocks outbound traffic to "
        "many ML endpoints; this prototype calls the hosted Gemini API, so a production deployment would "
        "allowlist it or run an Azure-hosted / on-prem model. (b) The rate limiter is in-memory and "
        "single-instance; behind multiple instances it would move to a shared store such as Redis. (c) Nothing is "
        'persisted, matching "we\'re not storing anything sensitive." (d) Typography rules — bold, minimum type '
        "size, placement — are not verifiable from extracted text and are left to the reviewer's eye. (e) The "
        "reviewer enters the expected (application) values by hand; auto-reading the COLA application form "
        "(Form 5100.31) to pre-fill them — a true two-document comparison — is the natural next step, left out "
        "because the brief calls for a standalone proof-of-concept, not a COLA-system integration."
    ),
    P("<b>Validated, not asserted.</b> The decisions above are backed by evidence rather than claims:"),
    P(
        "Extraction accuracy is 100% on the labeled eval set (418/418 fields across 32 synthetic cases); the "
        "same harness reports p50/p95 latency (currently p95 ≈ 3.2s) and flags anything over the 5-second bar.",
        "bullet",
    ),
    P(
        "127 automated tests (unit + API) plus ruff linting run in CI on pushes to main and on every pull "
        "request; the rule-based validation engine — the core compliance logic — is the most heavily tested module.",
        "bullet",
    ),
    P(
        "Uploads are screened three ways (file extension, content-type, and magic-byte signature) with a 10 MB "
        "cap; the API is rate-limited per IP (429s carry a Retry-After header) and sends standard security headers.",
        "bullet",
    ),
    P("The prototype is deployed to a public URL and has been verified end-to-end against a live label.", "bullet"),
]

build("docs/README.pdf", "Alcohol Label Verification - README", readme)
build("docs/Design-Document.pdf", "Alcohol Label Verification - Design Document", design)
