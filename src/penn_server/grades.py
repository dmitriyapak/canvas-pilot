"""Local what-if calculations; never writes hypothetical scores to Canvas."""

from math import isfinite


def calculate(groups, scores, weighted):
    """Calculate current graded-work percentage with Canvas-style group drops.

    Drop selection minimizes/maximizes the retained group ratio, which handles
    unequal point values. Canvas's reported grade remains authoritative.
    """
    totals = []
    for group in groups:
        items = []
        for assignment in group.get("assignments", []):
            submission = assignment.get("submission") or {}
            if submission.get("excused") or assignment.get("omit_from_final_grade"):
                continue
            points = assignment.get("points_possible")
            score = scores.get(str(assignment["id"]), submission.get("score"))
            if score is None or not isinstance(points, (float, int)) or points < 0:
                continue
            score = float(score)
            if not isfinite(score):
                raise ValueError("Scores must be finite numbers")
            items.append(
                dict(id=str(assignment["id"]), score=score, points=float(points))
            )
        rules = group.get("rules") or {}
        never = {str(x) for x in rules.get("never_drop", [])}
        dropped = []
        for kind in ("drop_lowest", "drop_highest"):
            for _ in range(int(rules.get(kind, 0))):
                candidates = []
                for i, item in enumerate(items):
                    if item["id"] in never or len(items) <= 1:
                        continue
                    others = items[:i] + items[i + 1 :]
                    denominator = sum(x["points"] for x in others)
                    if denominator <= 0:
                        continue
                    candidates.append(
                        (sum(x["score"] for x in others) / denominator, i)
                    )
                if not candidates:
                    break
                _, index = max(candidates) if kind == "drop_lowest" else min(candidates)
                dropped.append(items.pop(index)["id"])
        earned = sum(x["score"] for x in items)
        possible = sum(x["points"] for x in items)
        totals.append(
            dict(
                id=str(group["id"]),
                weight=group.get("group_weight", 0),
                earned=earned,
                possible=possible,
                dropped=dropped,
            )
        )
    if weighted:
        included = [g for g in totals if g["possible"] > 0 and g["weight"] > 0]
        denominator = sum(g["weight"] for g in included)
        percent = (
            sum(g["earned"] / g["possible"] * g["weight"] for g in included)
            / denominator
            * 100
            if denominator
            else None
        )
    else:
        possible = sum(g["possible"] for g in totals)
        percent = (
            sum(g["earned"] for g in totals) / possible * 100 if possible else None
        )
    return {
        "estimated_percent": percent,
        "groups": totals,
        "authoritative": False,
        "limitations": [
            "Current graded work only unless hypothetical scores are supplied.",
            "Grading periods, hidden grades and institutional overrides may differ from this estimate.",
            "Canvas-reported grades remain authoritative.",
        ],
    }
