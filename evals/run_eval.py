"""Run the extraction-accuracy eval.

Usage (from the repository root, with GEMINI_API_KEY set):

    venv/bin/python -m evals.run_eval                   # all cases, unified schema (the production default)
    venv/bin/python -m evals.run_eval --schema focused  # schema scoped to the case's known category
    venv/bin/python -m evals.run_eval --limit 5         # cheap partial run
    venv/bin/python -m evals.run_eval --case domestic-ipa-series

Each case is rendered to evals/images/<name>.png, sent through the production
extraction path, and scored. The default --schema unified mirrors what /extract
and /verify ship when no category is chosen: one all-fields extraction followed
by rule-based category/origin classification (app/classify.py), which is scored
against the case's ground truth alongside the fields. --schema focused instead
scopes the response schema to the case's known category — the path an explicit
reviewer selection takes. A summary plus every field-level miss, spurious field,
and classification miss is printed, and full results are written to
evals/last_results.json.
"""

import argparse
import asyncio
import json
import math
import time
from pathlib import Path

import app.extraction as extraction
from app.classify import classify_category, classify_origin
from app.errors import AppError
from app.extraction import _generation_config, build_contents, run_extraction

from .render import render_label
from .score import FIELDS, aggregate, score_case

# The stakeholder bar: a label should extract in about this many seconds.
LATENCY_BAR_SECONDS = 5.0

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


async def _extract_for_case(case, schema):
    png = render_label(case["artwork_lines"])
    IMAGES_DIR.mkdir(exist_ok=True)
    (IMAGES_DIR / f"{case['name']}.png").write_bytes(png)
    # "unified" mirrors the shipped default (/extract and /verify auto-detect):
    # extract every field at once, classify afterwards. "focused" feeds the
    # case's known category in, scoping the schema the way an explicit reviewer
    # selection does.
    category = case["product_category"] if schema == "focused" else None
    config = _generation_config(category)
    return await run_extraction(build_contents([(png, "image/png")]), config)


def _pct(ok, total):
    return f"{(100.0 * ok / total):5.1f}%" if total else "  n/a"


def _percentile(values, pct):
    """Ceiling-rank percentile over a list of seconds (no numpy dependency).

    Ceil-rank (index ceil(p·n)−1) never reads below the true percentile at small
    n, which matters because p95 is judged against the hard 5s bar — a
    rounded-rank estimate can drop a slow outlier and pass a run that should
    fail."""
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, math.ceil((pct / 100.0) * len(ordered)) - 1)
    return ordered[min(k, len(ordered) - 1)]


async def main_async(limit, only, schema):
    cases = _load_cases(limit, only)
    case_scores = []
    failures = []
    spurious = []
    classification_misses = []
    errors = []
    latencies = []

    print(f"Running {len(cases)} case(s) with the {schema} schema...\n")
    for index, case in enumerate(cases, 1):
        name = case["name"]
        # Wall-clock the whole extraction path, the same one the API serves. The
        # tiny render step is included but is negligible (~ms) next to the call.
        start = time.monotonic()
        try:
            extracted = await _extract_for_case(case, schema)
        except AppError as exc:
            elapsed = time.monotonic() - start
            latencies.append(elapsed)
            errors.append({"case": name, "code": exc.code, "seconds": round(elapsed, 2)})
            print(f"[{index}/{len(cases)}] {name}: EXTRACTION ERROR {exc.code} ({elapsed:.1f}s)")
            continue
        elapsed = time.monotonic() - start
        latencies.append(elapsed)

        # Fields are always scored against the case's known category so the
        # comparison rules (e.g. wine ABV tolerance) match the ground truth even
        # when classification gets the category wrong — that miss is scored on
        # its own line below, not by silently changing the field rules.
        result = score_case(case["product_category"], case["expected"], extracted)
        if schema == "unified":
            # Production classifies from the unified extraction, so score that
            # step too — a right-fields/wrong-category run must not look green.
            got_category = classify_category(extracted)
            got_origin = classify_origin(extracted)
            result["classification"] = {
                "category": {
                    "ok": got_category == case["product_category"],
                    "expected": case["product_category"],
                    "got": got_category,
                },
                "origin": {
                    "ok": got_origin == case["origin_type"],
                    "expected": case["origin_type"],
                    "got": got_origin,
                },
            }
        case_scores.append((name, result))

        n_ok = sum(1 for info in result["fields"].values() if info["ok"])
        notes = []
        if result["spurious"]:
            notes.append(f"{len(result['spurious'])} spurious")
        cls = result.get("classification")
        if cls and not (cls["category"]["ok"] and cls["origin"]["ok"]):
            notes.append("misclassified")
        note = f", {', '.join(notes)}" if notes else ""
        flag = "  ⚠ over bar" if elapsed > LATENCY_BAR_SECONDS else ""
        print(f"[{index}/{len(cases)}] {name}: {n_ok}/{len(result['fields'])} fields correct{note} ({elapsed:.1f}s){flag}")
        for field, info in result["fields"].items():
            if not info["ok"]:
                failures.append({"case": name, "field": field, "expected": info["expected"], "got": info["got"]})
        for field, got in result["spurious"].items():
            spurious.append({"case": name, "field": field, "got": got})
        if cls:
            for kind in ("category", "origin"):
                if not cls[kind]["ok"]:
                    classification_misses.append(
                        {"case": name, "kind": kind, "expected": cls[kind]["expected"], "got": cls[kind]["got"]}
                    )

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
    print(f"  Spurious fields:   {summary['spurious_total']} (in {summary['spurious_cases']} case(s))")
    if summary["classification"]:
        cls_stats = summary["classification"]
        print(f"  Classification:   category {_pct(cls_stats['category_ok'], cls_stats['total'])}  "
              f"({cls_stats['category_ok']}/{cls_stats['total']})  ·  "
              f"origin {_pct(cls_stats['origin_ok'], cls_stats['total'])}  "
              f"({cls_stats['origin_ok']}/{cls_stats['total']})")
    if errors:
        print(f"  Extraction errors: {len(errors)}")

    latency_stats = None
    if latencies:
        over_bar = sum(1 for s in latencies if s > LATENCY_BAR_SECONDS)
        latency_stats = {
            "count": len(latencies),
            "p50": round(_percentile(latencies, 50), 2),
            "p95": round(_percentile(latencies, 95), 2),
            "max": round(max(latencies), 2),
            "mean": round(sum(latencies) / len(latencies), 2),
            "over_bar": over_bar,
            "bar_seconds": LATENCY_BAR_SECONDS,
        }
        print("\n" + "=" * 60)
        print(f"LATENCY (bar: {LATENCY_BAR_SECONDS:.0f}s per label)")
        print("=" * 60)
        print(f"  p50:  {latency_stats['p50']:6.2f}s")
        print(f"  p95:  {latency_stats['p95']:6.2f}s")
        print(f"  max:  {latency_stats['max']:6.2f}s")
        print(f"  mean: {latency_stats['mean']:6.2f}s")
        print(f"  over {LATENCY_BAR_SECONDS:.0f}s: {over_bar}/{len(latencies)}")
        if latency_stats["p95"] > LATENCY_BAR_SECONDS:
            print(f"  ⚠ p95 ({latency_stats['p95']:.2f}s) EXCEEDS the {LATENCY_BAR_SECONDS:.0f}s bar")
        else:
            print(f"  ✓ p95 within the {LATENCY_BAR_SECONDS:.0f}s bar")

    if failures:
        print("\n" + "=" * 60)
        print(f"FIELD MISSES ({len(failures)})")
        print("=" * 60)
        for miss in failures:
            print(f"  {miss['case']} / {miss['field']}")
            print(f"      expected: {miss['expected']!r}")
            print(f"      got:      {miss['got']!r}")

    if spurious:
        print("\n" + "=" * 60)
        print(f"SPURIOUS FIELDS ({len(spurious)})")
        print("=" * 60)
        for item in spurious:
            print(f"  {item['case']} / {item['field']}")
            print(f"      extracted: {item['got']!r} (ground truth has no such field)")

    if classification_misses:
        print("\n" + "=" * 60)
        print(f"CLASSIFICATION MISSES ({len(classification_misses)})")
        print("=" * 60)
        for miss in classification_misses:
            print(f"  {miss['case']} / {miss['kind']}")
            print(f"      expected: {miss['expected']!r}")
            print(f"      got:      {miss['got']!r}")

    RESULTS_PATH.write_text(json.dumps(
        {
            "schema": schema,
            "summary": summary,
            "latency": latency_stats,
            "failures": failures,
            "spurious": spurious,
            "classification_misses": classification_misses,
            "errors": errors,
        },
        indent=2,
    ))
    print(f"\nFull results written to {RESULTS_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Run the extraction-accuracy eval.")
    parser.add_argument("--limit", type=int, default=None, help="run only the first N cases")
    parser.add_argument("--case", action="append", dest="only", default=None, help="run only this case name (repeatable)")
    parser.add_argument("--prompt-file", default=None, help="override EXTRACTION_PROMPT with the contents of this file (for A/B testing prompts)")
    parser.add_argument(
        "--schema",
        choices=("focused", "unified"),
        default="unified",
        help="extraction schema: 'unified' (all fields + scored classification — the production /extract and /verify "
        "default) or 'focused' (scoped to the case's known category)",
    )
    args = parser.parse_args()
    if args.prompt_file:
        extraction.EXTRACTION_PROMPT = Path(args.prompt_file).read_text()
        print(f"(using prompt override: {args.prompt_file})")
    asyncio.run(main_async(args.limit, args.only, args.schema))


if __name__ == "__main__":
    main()
