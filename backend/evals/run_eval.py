"""Run the extraction-accuracy eval.

Usage (from the backend/ directory, with GEMINI_API_KEY set):

    venv/bin/python -m evals.run_eval            # run all cases
    venv/bin/python -m evals.run_eval --limit 5  # cheap partial run
    venv/bin/python -m evals.run_eval --case domestic-ipa-series

Each case is rendered to evals/images/<name>.png, sent through the production
extraction path, and scored. A summary plus every field-level miss is printed,
and full results are written to evals/last_results.json.
"""

import argparse
import asyncio
import json
from pathlib import Path

import app.extraction as extraction
from app.errors import AppError
from app.extraction import _generation_config, build_contents, run_extraction

from .render import render_label
from .score import FIELDS, aggregate, score_case

EVAL_DIR = Path(__file__).resolve().parent
CASES_PATH = EVAL_DIR / "cases.json"
IMAGES_DIR = EVAL_DIR / "images"
RESULTS_PATH = EVAL_DIR / "last_results.json"


def _load_cases(limit, only):
    if not CASES_PATH.exists():
        raise SystemExit(f"No cases file at {CASES_PATH}. Generate it first.")
    cases = json.loads(CASES_PATH.read_text())["cases"]
    if only:
        cases = [c for c in cases if c["name"] in set(only)]
    if limit:
        cases = cases[:limit]
    if not cases:
        raise SystemExit("No matching cases to run.")
    return cases


async def _extract_for_case(case):
    png = render_label(case["artwork_lines"])
    IMAGES_DIR.mkdir(exist_ok=True)
    (IMAGES_DIR / f"{case['name']}.png").write_bytes(png)
    config = _generation_config(case["product_category"])
    return await run_extraction(build_contents([(png, "image/png")]), config)


def _pct(ok, total):
    return f"{(100.0 * ok / total):5.1f}%" if total else "  n/a"


async def main_async(limit, only):
    cases = _load_cases(limit, only)
    case_scores = []
    failures = []
    errors = []

    print(f"Running {len(cases)} case(s)...\n")
    for index, case in enumerate(cases, 1):
        name = case["name"]
        try:
            extracted = await _extract_for_case(case)
        except AppError as exc:
            errors.append({"case": name, "code": exc.code})
            print(f"[{index}/{len(cases)}] {name}: EXTRACTION ERROR {exc.code}")
            continue

        result = score_case(case["product_category"], case["expected"], extracted)
        case_scores.append((name, result))
        n_ok = sum(1 for info in result.values() if info["ok"])
        print(f"[{index}/{len(cases)}] {name}: {n_ok}/{len(result)} fields correct")
        for field, info in result.items():
            if not info["ok"]:
                failures.append({"case": name, "field": field, "expected": info["expected"], "got": info["got"]})

    summary = aggregate(case_scores)

    print("\n" + "=" * 60)
    print("PER-FIELD ACCURACY")
    print("=" * 60)
    for field in [f for f in FIELDS if f in summary["per_field"]] + [f for f in summary["per_field"] if f not in FIELDS]:
        stats = summary["per_field"][field]
        print(f"  {field:<28} {_pct(stats['ok'], stats['total'])}  ({stats['ok']}/{stats['total']})")

    print("\n" + "=" * 60)
    print("OVERALL")
    print("=" * 60)
    print(f"  Field accuracy:   {_pct(summary['field_ok'], summary['field_total'])}  ({summary['field_ok']}/{summary['field_total']})")
    print(f"  Cases all-correct: {summary['case_pass']}/{summary['case_total']}")
    if errors:
        print(f"  Extraction errors: {len(errors)}")

    if failures:
        print("\n" + "=" * 60)
        print(f"FIELD MISSES ({len(failures)})")
        print("=" * 60)
        for miss in failures:
            print(f"  {miss['case']} / {miss['field']}")
            print(f"      expected: {miss['expected']!r}")
            print(f"      got:      {miss['got']!r}")

    RESULTS_PATH.write_text(json.dumps(
        {"summary": summary, "failures": failures, "errors": errors},
        indent=2,
    ))
    print(f"\nFull results written to {RESULTS_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Run the extraction-accuracy eval.")
    parser.add_argument("--limit", type=int, default=None, help="run only the first N cases")
    parser.add_argument("--case", action="append", dest="only", default=None, help="run only this case name (repeatable)")
    parser.add_argument("--prompt-file", default=None, help="override EXTRACTION_PROMPT with the contents of this file (for A/B testing prompts)")
    args = parser.parse_args()
    if args.prompt_file:
        extraction.EXTRACTION_PROMPT = Path(args.prompt_file).read_text()
        print(f"(using prompt override: {args.prompt_file})")
    asyncio.run(main_async(args.limit, args.only))


if __name__ == "__main__":
    main()
