# Extraction-accuracy eval

Measures whether Gemini, via the production prompt and extraction path, pulls the
**right** field values off label artwork — the assumption the whole tool rests on.

## Run

From the repository root with `GEMINI_API_KEY` set (each case is one live Gemini call):

```bash
venv/bin/python -m evals.run_eval              # all cases
venv/bin/python -m evals.run_eval --limit 5    # cheap partial run
venv/bin/python -m evals.run_eval --case domestic-ipa-series
venv/bin/python -m evals.run_eval --schema focused   # legacy category-scoped schema
```

By default (`--schema unified`) each case is extracted with the all-fields schema
— the same path production takes when category/origin are on Auto — and the
deterministic classifier (`app/classify.py`) is scored against the case's known
category and origin. `--schema focused` keeps the old category-scoped extraction
for apples-to-apples comparison with pre-unified baselines.

Output: per-field accuracy, overall field accuracy, count of fully-correct cases,
every field-level miss (expected vs got), classification accuracy (unified mode),
and any **spurious fields** — non-empty extractions in fields the ground truth
says should be absent (these fail the case but don't change the headline
field-accuracy denominator). Full results land in `evals/last_results.json`;
rendered artwork in `evals/images/`.

## How it works

- `cases.json` — ground-truth cases: `artwork_lines` (rendered top-to-bottom) plus
  the `expected` field values a correct extraction should produce. Authored and
  cross-checked against the prompt rules and the TTB checklists.
- `render.py` — turns `artwork_lines` into a plain PNG (black text on white).
- `score.py` — scores each extracted field against ground truth using the same
  `validation.match_field` the tool uses for verdicts, so a "correct" field means
  the tool would render the right result. The government warning is scored with
  the statutory-text check.

## Limitations

- **Synthetic artwork.** Cases are rendered text, not photographs of real labels,
  so this measures the model's field *separation and extraction* logic (the
  prompt's hard part), not OCR robustness on curved bottles, foil, or low-res
  scans. Add real labeled cases to `cases.json` to extend coverage.
- **No typography.** Bold / type-size / "separate and apart" warning rules are not
  representable here (a known tool limitation, not just an eval one).
- Scoring inherits the comparator's tolerances (ABV bands, unit conversion), by
  design — it reflects the verdict the tool would actually give.
