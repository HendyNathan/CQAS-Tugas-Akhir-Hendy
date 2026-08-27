"""Document extraction and field normalization for Indonesian/English lab reports."""
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

FIELD_SYNONYMS = {
    "record_number": ["no", "nomor", "number", "record", "no sampel"],
    "sample_code": ["code", "sample code", "sample id", "id", "specimen", "kode", "kode sampel", "kode benda uji", "benda uji"],
    "casting_date": ["casting date", "cast date", "tanggal cor", "tgl cor", "cor", "casting"],
    "test_date": ["test date", "testing date", "tanggal uji", "tgl uji", "tanggal", "date", "test"],
    "age_days": ["age", "age days", "umur", "umur hari", "umur beton", "hari", "days", "test age"],
    "cross_section_area": ["area", "cross section", "cross-sectional area", "section area", "luas", "luas penampang"],
    "weight": ["weight", "mass", "berat", "berat benda uji"],
    "load": ["load", "maximum load", "max load", "beban", "beban maksimum", "beban maks"],
    "compressive_strength": ["compressive strength", "strength", "concrete strength", "compressive", "kuat tekan", "mutu beton", "nilai kuat tekan", "hasil kuat tekan", "fc", "f'c", "mpa", "n/mm"],
    "crack_pattern": ["crack pattern", "failure pattern", "pattern", "pola retak", "pola keretakan", "pola pecah"],
    "notes": ["notes", "note", "remark", "remarks", "description", "keterangan", "catatan", "ket"],
    "actual_slump": ["slump", "slump test", "slump value", "slump aktual", "aktual slump", "slump actual", "nilai slump", "hasil slump"],
    "target_slump": ["target slump", "slump rencana", "planned slump", "slump target"],
    "planned_strength": ["plan", "planned", "design", "design strength", "planned strength", "rencana", "nilai rencana", "mutu rencana", "target", "target value"],
}

def clean_header(value: Any) -> str:
    """Collapse OCR spacing/punctuation and normalize common accents."""
    text = str(value or "").lower().replace("²", "2").replace("’", "'")
    text = re.sub(r"[^a-z0-9'/]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, clean_header(a).replace(" ", ""), clean_header(b).replace(" ", "")).ratio()

def map_header(header: Any) -> tuple[str | None, float]:
    normalized = clean_header(header)
    best_field, best_score = None, 0.0
    for field, terms in FIELD_SYNONYMS.items():
        for term in terms:
            score = 1.0 if normalized == clean_header(term) else similarity(normalized, term)
            if clean_header(term) in normalized and len(clean_header(term)) > 3:
                score = max(score, 0.92)
            if score > best_score:
                best_field, best_score = field, score
    return (best_field, round(best_score, 2)) if best_score >= 0.58 else (None, round(best_score, 2))

def detect_header_row(rows: list[list[Any]]) -> int:
    best_index, best_hits = 0, -1
    for index, row in enumerate(rows[:30]):
        hits = sum(1 for cell in row if map_header(cell)[0])
        if hits > best_hits:
            best_index, best_hits = index, hits
    return best_index

def parse_number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().replace(" ", "")
    # Indonesian decimal comma is supported while preserving a simple thousands case.
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    text = re.sub(r"[^0-9.\-]", "", text)
    try:
        return float(text) if text else None
    except ValueError:
        return None

def parse_date(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return pd.to_datetime(value, dayfirst=True).date().isoformat()
    except (ValueError, TypeError):
        return None

def infer_unit(header: str, value: Any) -> str | None:
    text = f"{header} {value}".lower().replace("²", "2")
    for unit in ("n/mm2", "mpa", "kgf/cm2", "kg/cm2", "psi", "kn", "mm", "cm", "kg", "g"):
        if unit in text:
            return unit
    return None

def normalize_record(raw: dict[str, Any], headers: dict[str, str], source: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {"raw_values": raw, "original_headers": headers, "source": source}
    for field, value in raw.items():
        if field in {"age_days", "cross_section_area", "weight", "load", "compressive_strength", "planned_strength", "actual_slump", "target_slump"}:
            record[field] = parse_number(value)
        elif field in {"casting_date", "test_date"}:
            record[field] = parse_date(value)
        else:
            record[field] = str(value).strip() if value is not None else None
    if record.get("casting_date") and record.get("test_date"):
        try:
            start = datetime.fromisoformat(record["casting_date"])
            end = datetime.fromisoformat(record["test_date"])
            record["calculated_age_days"] = (end - start).days
            if record.get("age_days") is not None and abs(record["age_days"] - record["calculated_age_days"]) > 2:
                record.setdefault("warnings", []).append("Potential date/age inconsistency.")
        except ValueError:
            pass
    if record.get("compressive_strength") is None and record.get("load") and record.get("cross_section_area"):
        area_mm2 = record["cross_section_area"] * 100 if "cm" in str(headers.get("cross_section_area", "")).lower() else record["cross_section_area"]
        record["derived_strength"] = round((record["load"] * 1000) / area_mm2, 2) if area_mm2 else None
        record.setdefault("warnings", []).append("Compressive strength was derived from load and area.")
    return record

def rows_to_records(rows: list[list[Any]], source: dict[str, Any]) -> dict[str, Any]:
    header_row = detect_header_row(rows)
    source_headers = [str(cell or "").strip() for cell in rows[header_row]]
    mapped: dict[int, tuple[str, float]] = {}
    used, unused = [], []
    for index, header in enumerate(source_headers):
        field, confidence = map_header(header)
        if field:
            mapped[index] = (field, confidence)
            used.append({"header": header, "field": field, "confidence": confidence})
        else:
            unused.append(header)
    records = []
    for row_number, row in enumerate(rows[header_row + 1:], header_row + 2):
        if not any(str(cell or "").strip() for cell in row):
            continue
        raw, headers = {}, {}
        confidence = []
        for index, (field, score) in mapped.items():
            value = row[index] if index < len(row) else None
            raw[field] = value
            headers[field] = source_headers[index]
            confidence.append(score)
        if raw:
            records.append(normalize_record(raw, headers, {**source, "row": row_number}))
            records[-1]["confidence"] = round(sum(confidence) / len(confidence) * 100, 0) if confidence else 0
    return {"header_row": header_row + 1, "used_columns": used, "unused_columns": unused, "records": records}

def extract_excel(data: bytes, filename: str) -> dict[str, Any]:
    workbook = pd.ExcelFile(io.BytesIO(data))
    sheets = []
    all_records = []
    for sheet in workbook.sheet_names:
        values = pd.read_excel(io.BytesIO(data), sheet_name=sheet, header=None).fillna("").values.tolist()
        result = rows_to_records(values, {"file": filename, "sheet": sheet, "method": "excel"})
        sheets.append({"sheet": sheet, **{k: result[k] for k in ("header_row", "used_columns", "unused_columns")}})
        all_records.extend(result["records"])
    return {"kind": "excel", "sheets": sheets, "records": all_records, "detected": len(all_records)}

def extract_pdf(data: bytes, filename: str) -> dict[str, Any]:
    import pdfplumber
    all_records, pages = [], []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables() or []
            for table in tables:
                result = rows_to_records(table, {"file": filename, "page": page_number, "method": "pdf-text"})
                all_records.extend(result["records"])
                pages.append({"page": page_number, "used_columns": result["used_columns"], "unused_columns": result["unused_columns"]})
    return {"kind": "pdf", "pages": pages, "records": all_records, "detected": len(all_records), "ocr_note": "Scanned pages without an extractable text layer require OCR verification."}

def extract_document(data: bytes, filename: str) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return extract_excel(data, filename)
    if suffix == ".pdf":
        return extract_pdf(data, filename)
    raise ValueError("Supported files are PDF, XLSX, and XLS.")