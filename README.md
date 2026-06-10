# Treasury DOGE Alcohol Label Verification

AI-powered alcohol label verification prototype for comparing alcohol label artwork against expected COLA/application fields.

## Project Layout

```text
pyproject.toml       Vercel deployment metadata and runtime dependencies
.python-version      Python version for deployment
backend/
  app/
    clients.py       Gemini client and environment loading
    extraction.py    Image-to-JSON extraction workflow
    main.py          FastAPI routes
    prompts.py       Label extraction prompt
    schemas.py       Request models and enums
    validation.py    Compliance comparison helpers
  scripts/
    gemini_smoke_test.py
  tests/
    test_validation.py
  main_gemini.py     Compatibility entrypoint for older run commands
  requirements.txt
```

## Setup

Create a local environment file:

```bash
cp backend/.env.example backend/.env
```

Then edit `backend/.env` and set `GEMINI_API_KEY`.

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

## UI

The minimal UI is served by FastAPI from `backend/app/static/`. It supports:

- Product category and origin toggles.
- Front/back label uploads.
- Dynamic required, conditional, and optional field lists.
- Reviewed-field verification without re-running extraction.
- Light/dark mode with local browser preference storage.

## API

- `GET /field-requirements` returns required, conditional, and optional fields for a `product_category` and `origin_type`.
- `POST /extract` extracts label fields from uploaded artwork.
- `POST /verify` extracts fields from uploaded artwork and validates them against expected application values.
- `POST /verify-reviewed` validates reviewed/corrected fields without making another Gemini call.

Upload endpoints accept PDF, PNG, JPEG, and WebP files up to 10 MB each. Upload validation checks the file extension, browser-provided content type, and file signature before sending anything to Gemini. API errors use this shape:

```json
{
  "error": {
    "code": "GEMINI_INVALID_JSON",
    "message": "Gemini returned a response that could not be parsed as JSON.",
    "details": {}
  }
}
```

## Vercel Deployment

The repo is prepared for Vercel with:

- `pyproject.toml`, including runtime dependencies and an `app` script pointing to `backend.app.main:app`.
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
