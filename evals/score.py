"""Score extracted fields against ground truth.

Uses the production comparison logic (validation.match_field) so a field counts
as correct when the tool would call it a match — i.e. this measures end-to-end
"would the verdict be right", not raw string equality. The government warning is
scored with the same statutory-text check the tool uses.

Fields the ground truth never mentions are checked the other way: a non-empty
extraction there is *spurious* (the model invented or misplaced a value). A
spurious field fails the case but is reported separately, outside the headline
field-accuracy numbers, so that metric's denominator (the cases' expected
fields) stays comparable across runs.
"""

from app.schemas import LabelFields
from app.validation import check_government_warning, match_field

FIELDS = tuple(LabelFields.model_fields)


def _is_empty(value):
    return not (value or "").strip()


def score_case(product_category, expected, extracted):
    """Score one case. Returns
    {"fields": {field: {"ok": bool, "expected": str, "got": str}}, "spurious": {field: got}}.

    "fields" scores only the fields the case's ground truth specifies, so older
    cases that list the original 11 fields and newer cases that list more are
    both handled. "spurious" covers the rest: any non-empty extraction in a field
    the ground truth omits entirely. Fields the ground truth lists as "" are not
    spurious — they are scored as must-be-absent in "fields".
    """
    fields = {}
    for field in expected:
        exp = expected.get(field) or ""
        got = extracted.get(field) or ""

        if field == "government_warning":
            if _is_empty(exp):
                ok = _is_empty(got)
            else:
                # Score by verdict parity, not "must PASS": the tool must reach the
                # same compliance verdict on the extracted text as on the ground
                # truth. For a deliberately non-compliant label (title-case heading,
                # altered punctuation) the model must transcribe it verbatim — if it
                # "helpfully" corrects the text, the verdict flips and we catch it.
                ok = check_government_warning(got) == check_government_warning(exp)
        elif _is_empty(exp):
            # Field should be absent — correct only if the model also left it empty.
            ok = _is_empty(got)
        else:
            ok = match_field(field, product_category, exp, got) == "PASS"

        fields[field] = {"ok": ok, "expected": exp, "got": got}

    spurious = {
        field: got
        for field, got in extracted.items()
        if field not in expected and not _is_empty(got)
    }
    return {"fields": fields, "spurious": spurious}


def aggregate(case_scores):
    """case_scores: list of (case_name, score_case result). Returns summary stats.

    A result may also carry a "classification" entry (attached by the runner in
    unified mode, with "category"/"origin" each {"ok", "expected", "got"}); it is
    tallied separately, and a misclassification fails the case the same way a
    spurious field does. Neither touches field_ok/field_total — the headline
    accuracy covers only the ground-truth fields.
    """
    per_field = {}
    field_ok = 0
    field_total = 0
    case_pass = 0
    spurious_total = 0
    spurious_cases = 0
    classification = None

    for _name, result in case_scores:
        all_ok = True
        for field, info in result["fields"].items():
            stats = per_field.setdefault(field, {"ok": 0, "total": 0})
            stats["total"] += 1
            field_total += 1
            if info["ok"]:
                stats["ok"] += 1
                field_ok += 1
            else:
                all_ok = False
        if result["spurious"]:
            spurious_total += len(result["spurious"])
            spurious_cases += 1
            all_ok = False
        cls = result.get("classification")
        if cls is not None:
            if classification is None:
                classification = {"category_ok": 0, "origin_ok": 0, "total": 0}
            classification["total"] += 1
            classification["category_ok"] += 1 if cls["category"]["ok"] else 0
            classification["origin_ok"] += 1 if cls["origin"]["ok"] else 0
            if not (cls["category"]["ok"] and cls["origin"]["ok"]):
                all_ok = False
        if all_ok:
            case_pass += 1

    return {
        "per_field": per_field,
        "field_ok": field_ok,
        "field_total": field_total,
        "case_pass": case_pass,
        "case_total": len(case_scores),
        "spurious_total": spurious_total,
        "spurious_cases": spurious_cases,
        "classification": classification,
    }
