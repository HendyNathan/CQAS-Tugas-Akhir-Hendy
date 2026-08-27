"""Deterministic engineering assessment, anomaly, and recommendation rules."""
from datetime import datetime, timezone

def assess_slump(row: dict, settings: dict) -> dict:
    actual, target = row.get("actual_slump"), row.get("target_slump") or settings.get("target_slump")
    minimum, maximum = settings.get("min_slump"), settings.get("max_slump")
    if actual is None:
        return {"status": "INSUFFICIENT DATA", "reason": "Actual slump is missing.", "rule": "slump.actual.required"}
    deviation = round(actual - target, 2) if target is not None else None
    row["deviation"] = deviation
    if minimum is not None and actual < minimum:
        return {"status": "NON-COMPLIANT", "reason": "Actual slump is below the configured minimum acceptance limit.", "rule": "slump.minimum"}
    if maximum is not None and actual > maximum:
        return {"status": "NON-COMPLIANT", "reason": "Actual slump is above the configured maximum acceptance limit.", "rule": "slump.maximum"}
    if target is None:
        return {"status": "WARNING", "reason": "Target slump is missing; verify against project criteria.", "rule": "slump.target.missing"}
    return {"status": "COMPLIANT", "reason": "Actual slump is within the configured acceptance criteria.", "rule": "slump.range"}

def assess_strength(row: dict, settings: dict) -> dict:
    actual = row.get("compressive_strength") or row.get("derived_strength")
    planned = row.get("planned_strength") or settings.get("design_strength")
    if actual is None:
        return {"status": "INSUFFICIENT DATA", "reason": "Compressive strength is missing.", "rule": "strength.actual.required"}
    if planned is None:
        return {"status": "WARNING", "reason": "Design strength is missing; verify against project criteria.", "rule": "strength.planned.missing"}
    row["difference"] = round(actual - planned, 2)
    row["achievement_pct"] = round(actual / planned * 100, 1) if planned else None
    if actual < planned:
        return {"status": "WARNING", "reason": "Actual strength is below the design value and requires verification.", "rule": "strength.design"}
    return {"status": "COMPLIANT", "reason": "Actual strength meets or exceeds the design value.", "rule": "strength.design"}

def analyze(records: list[dict], test_type: str, settings: dict) -> dict:
    results, anomalies = [], []
    seen = set()
    for row in records:
        sample = row.get("sample_code") or row.get("record_number")
        if sample and sample in seen:
            anomalies.append({"type": "DUPLICATE", "message": f"Duplicate sample code: {sample}"})
        if sample: seen.add(sample)
        if row.get("warnings"): anomalies.extend({"type": "VERIFICATION", "message": warning} for warning in row["warnings"])
        if test_type == "slump": assessment = assess_slump(row, settings)
        else: assessment = assess_strength(row, settings)
        assessment.update({"timestamp": datetime.now(timezone.utc).isoformat(), "assessment_version": "1.0"})
        row["assessment"] = assessment
        results.append(row)
    counts = {key: sum(1 for r in results if r.get("assessment", {}).get("status") == key) for key in ("COMPLIANT", "WARNING", "NON-COMPLIANT", "INSUFFICIENT DATA")}
    return {"records": results, "anomalies": anomalies, "counts": counts}