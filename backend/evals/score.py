"""Score extracted fields against ground truth.

Uses the production comparison logic (validation.match_field) so a field counts
as correct when the tool would call it a match — i.e. this measures end-to-end
"would the verdict be right", not raw string equality. The government warning is
scored with the same statutory-text check the tool uses.
"""

from app.schemas import LabelFields
from app.validation import check_government_warning, match_field

FIELDS = tuple(LabelFields.model_fields)


def _is_empty(value):
    return not (value or "").strip()


def score_case(product_category, expected, extracted):
    """Return {field: {"ok": bool, "expected": str, "got": str}} for one case.

    Scores only the fields the case's ground truth specifies, so older cases that
    list the original 11 fields and newer cases that list more are both handled.
    """
    result = {}
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

        result[field] = {"ok": ok, "expected": exp, "got": got}
    return result


def aggregate(case_scores):
    """case_scores: list of (case_name, per_field_result). Returns summary stats."""
    per_field = {}
    field_ok = 0
    field_total = 0
    case_pass = 0

    for _name, result in case_scores:
        all_ok = True
        for field, info in result.items():
            stats = per_field.setdefault(field, {"ok": 0, "total": 0})
            stats["total"] += 1
            field_total += 1
            if info["ok"]:
                stats["ok"] += 1
                field_ok += 1
            else:
                all_ok = False
        if all_ok:
            case_pass += 1

    return {
        "per_field": per_field,
        "field_ok": field_ok,
        "field_total": field_total,
        "case_pass": case_pass,
        "case_total": len(case_scores),
    }
