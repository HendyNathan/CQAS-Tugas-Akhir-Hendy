"""Deterministic engineering assessment, anomaly, and recommendation rules.

Reasons use language-neutral `rule` codes so the frontend can translate them at render time.
"""
from datetime import datetime, timezone


RECOMMENDATIONS = {
    "slump.minimum": "recommendation.slump.low",
    "slump.maximum": "recommendation.slump.high",
    "slump.target.missing": "recommendation.slump.target_missing",
    "slump.actual.required": "recommendation.slump.actual_missing",
    "slump.range": "recommendation.slump.ok",
    "strength.actual.required": "recommendation.strength.actual_missing",
    "strength.planned.missing": "recommendation.strength.planned_missing",
    "strength.design": "recommendation.strength.review",
}


def _finish(assessment: dict) -> dict:
    assessment["recommendation_code"] = RECOMMENDATIONS.get(assessment.get("rule"))
    assessment["timestamp"] = datetime.now(timezone.utc).isoformat()
    assessment["assessment_version"] = "1.1"
    return assessment


def assess_slump(row: dict, settings: dict) -> dict:
    actual, target = row.get("actual_slump"), row.get("target_slump") or settings.get("target_slump")
    minimum, maximum = settings.get("min_slump"), settings.get("max_slump")
    if actual is None:
        return _finish({"status": "INSUFFICIENT DATA", "reason": "Actual slump is missing.", "rule": "slump.actual.required"})
    deviation = round(actual - target, 2) if target is not None else None
    row["deviation"] = deviation
    if minimum is not None and actual < minimum:
        return _finish({"status": "NON-COMPLIANT", "reason": "Actual slump is below the configured minimum acceptance limit.", "rule": "slump.minimum"})
    if maximum is not None and actual > maximum:
        return _finish({"status": "NON-COMPLIANT", "reason": "Actual slump is above the configured maximum acceptance limit.", "rule": "slump.maximum"})
    if target is None:
        return _finish({"status": "WARNING", "reason": "Target slump is missing; verify against project criteria.", "rule": "slump.target.missing"})
    return _finish({"status": "COMPLIANT", "reason": "Actual slump is within the configured acceptance criteria.", "rule": "slump.range"})


def assess_strength(row: dict, settings: dict) -> dict:
    actual = row.get("compressive_strength") or row.get("derived_strength")
    planned = row.get("planned_strength") or settings.get("design_strength")
    if actual is None:
        return _finish({"status": "INSUFFICIENT DATA", "reason": "Compressive strength is missing.", "rule": "strength.actual.required"})
    if planned is None:
        return _finish({"status": "WARNING", "reason": "Design strength is missing; verify against project criteria.", "rule": "strength.planned.missing"})
    row["difference"] = round(actual - planned, 2)
    row["achievement_pct"] = round(actual / planned * 100, 1) if planned else None
    if actual < planned:
        return _finish({"status": "WARNING", "reason": "Actual strength is below the design value and requires verification.", "rule": "strength.design"})
    return _finish({"status": "COMPLIANT", "reason": "Actual strength meets or exceeds the design value.", "rule": "strength.design"})


def analyze(records: list[dict], test_type: str, settings: dict) -> dict:
    results, anomalies = [], []
    seen = set()
    for row in records:
        sample = row.get("sample_code") or row.get("record_number")
        if sample and sample in seen:
            anomalies.append({"type": "DUPLICATE", "code": "anomaly.duplicate_sample", "params": {"sample": sample}, "message": f"Duplicate sample code: {sample}"})
        if sample:
            seen.add(sample)
        for warning in row.get("warnings", []) or []:
            if isinstance(warning, dict):
                anomalies.append({"type": "VERIFICATION", **warning})
            else:
                anomalies.append({"type": "VERIFICATION", "code": None, "params": {}, "message": str(warning)})
        assessment = assess_slump(row, settings) if test_type == "slump" else assess_strength(row, settings)
        row["assessment"] = assessment
        results.append(row)
    counts = {key: sum(1 for r in results if r.get("assessment", {}).get("status") == key) for key in ("COMPLIANT", "WARNING", "NON-COMPLIANT", "INSUFFICIENT DATA")}
    return {"records": results, "anomalies": anomalies, "counts": counts}
