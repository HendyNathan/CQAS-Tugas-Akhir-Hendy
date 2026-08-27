"""Document extraction with Indonesian/English fuzzy header mapping, OCR fallback,
and multi-table detection (Slump vs Compressive Strength)."""
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

FIELD_SYNONYMS: dict[str, list[str]] = {
    "record_number": ["no", "nomor", "number", "record", "no sampel"],
    "sample_code": ["code", "sample code", "sample id", "id", "specimen", "specimen id", "kode", "kode sampel", "kode benda uji", "benda uji"],
    "casting_date": ["casting date", "cast date", "date cor", "tanggal cor", "tgl cor", "cor", "casting"],
    "test_date": ["test date", "testing date", "tanggal uji", "tgl uji", "tanggal", "date test", "date", "test"],
    "age_days": ["age", "age days", "test age", "concrete age", "umur", "umur hari", "umur beton", "umur (hari)", "hari", "days"],
    "cross_section_area": ["area", "cross section", "cross section area", "cross-sectional area", "section area", "luas", "luas penampang"],
    "weight": ["weight", "mass", "berat", "berat benda uji"],
    "load": ["load", "maximum load", "max load", "beban", "beban maksimum", "beban maks"],
    "compressive_strength": ["compressive strength", "concrete strength", "compressive", "strength", "kuat tekan", "kuat tekan beton", "mutu beton", "nilai kuat tekan", "hasil kuat tekan", "fc", "f'c", "mpa", "n/mm2"],
    "planned_strength": ["planned strength", "design strength", "design", "planned", "plan", "rencana", "mutu rencana", "nilai rencana", "target strength", "target value", "target"],
    "actual_slump": ["slump", "slump test", "slump value", "slump aktual", "aktual slump", "slump actual", "nilai slump", "hasil slump", "slump beton"],
    "target_slump": ["target slump", "planned slump", "slump rencana", "slump target"],
    "supplier": ["supplier", "pemasok", "batching plant", "ready mix", "readymix"],
    "location": ["element", "location", "lokasi", "elemen", "struktur", "structure"],
    "concrete_grade": ["mutu", "mutu beton", "grade", "concrete grade", "class", "kelas"],
    "crack_pattern": ["crack pattern", "failure pattern", "pattern", "pola retak", "pola keretakan", "pola pecah"],
    "notes": ["notes", "note", "remark", "remarks", "description", "keterangan", "catatan", "ket"],
}

STRENGTH_FIELDS = {"compressive_strength", "planned_strength", "load", "cross_section_area", "age_days", "casting_date", "crack_pattern"}
SLUMP_FIELDS = {"actual_slump", "target_slump"}
NUMERIC_FIELDS = {"age_days", "cross_section_area", "weight", "load", "compressive_strength", "planned_strength", "actual_slump", "target_slump"}
DATE_FIELDS = {"casting_date", "test_date"}


def clean_header(value: Any) -> str:
    """Normalize header text so OCR spacing, punctuation, and unit hints do not break matching."""
    text = str(value or "").lower().replace("²", "2").replace("’", "'")
    text = re.sub(r"[^a-z0-9'/]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a.replace(" ", ""), b.replace(" ", "")).ratio()


def map_header(header: Any) -> tuple[str | None, float]:
    """Return the (field, confidence) that best matches the header, or (None, score)."""
    normalized = clean_header(header)
    if not normalized:
        return None, 0.0
    # Rules: strong keyword hints override generic synonym matches so 'slump target' does not
    # collide with 'planned strength'.
    if "slump" in normalized:
        if any(word in normalized for word in ("target", "rencana", "planned", "plan", "design")):
            return "target_slump", 0.98
        return "actual_slump", 0.95
    best_field, best_score = None, 0.0
    for field, terms in FIELD_SYNONYMS.items():
        for term in terms:
            clean_term = clean_header(term)
            score = 1.0 if normalized == clean_term else similarity(normalized, clean_term)
            if clean_term and clean_term in normalized and len(clean_term) > 2:
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
        return pd.to_datetime(str(value), dayfirst=True, errors="raise").date().isoformat()
    except (ValueError, TypeError):
        return None


def infer_unit(header: str, value: Any) -> str | None:
    text = f"{header} {value}".lower().replace("²", "2")
    for unit in ("n/mm2", "mpa", "kgf/cm2", "kg/cm2", "psi", "kn", "mm", "cm", "kg", "g"):
        if unit in text:
            return unit
    return None


def normalize_record(raw: dict[str, Any], headers: dict[str, str], source: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {"raw_values": {k: (str(v) if v is not None else "") for k, v in raw.items()}, "original_headers": headers, "source": source}
    for field, value in raw.items():
        if field in NUMERIC_FIELDS:
            record[field] = parse_number(value)
        elif field in DATE_FIELDS:
            record[field] = parse_date(value)
        else:
            record[field] = str(value).strip() if value is not None else None
    for field in ("compressive_strength", "planned_strength", "load"):
        header_text = headers.get(field, "")
        unit = infer_unit(header_text, raw.get(field, ""))
        if unit:
            record.setdefault("units", {})[field] = unit
    if record.get("casting_date") and record.get("test_date"):
        try:
            start = datetime.fromisoformat(record["casting_date"])
            end = datetime.fromisoformat(record["test_date"])
            record["calculated_age_days"] = (end - start).days
            if end < start:
                record.setdefault("warnings", []).append({"code": "date.test_before_casting", "params": {}, "message": "Test date is earlier than casting date."})
            if record.get("age_days") is not None and abs(record["age_days"] - record["calculated_age_days"]) > 2:
                record.setdefault("warnings", []).append({"code": "age.inconsistent", "params": {"calculated": record["calculated_age_days"], "extracted": record["age_days"]}, "message": f"Calculated age is approximately {record['calculated_age_days']} days, while extracted age is {record['age_days']} days. Verify test date, casting date, or age value."})
        except ValueError:
            pass
    if record.get("compressive_strength") is None and record.get("load") and record.get("cross_section_area"):
        area_header = str(headers.get("cross_section_area", "")).lower()
        area_mm2 = record["cross_section_area"] * 100 if "cm" in area_header else record["cross_section_area"]
        record["derived_strength"] = round((record["load"] * 1000) / area_mm2, 2) if area_mm2 else None
        record.setdefault("warnings", []).append({"code": "strength.derived", "params": {}, "message": "Compressive strength derived from load and area (CALCULATED FROM LOAD AND AREA)."})
    return record


def classify_table(field_set: set[str]) -> str:
    strength_hits = len(field_set & STRENGTH_FIELDS)
    slump_hits = len(field_set & SLUMP_FIELDS)
    if strength_hits >= slump_hits and strength_hits > 0:
        return "strength"
    if slump_hits > 0:
        return "slump"
    return "unknown"


def rows_to_table(rows: list[list[Any]], source: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a raw grid into normalized records plus mapping metadata for review."""
    if not rows or all(not any(str(cell or "").strip() for cell in row) for row in rows):
        return None
    header_row = detect_header_row(rows)
    source_headers = [str(cell or "").strip() for cell in rows[header_row]]
    mapped: dict[int, tuple[str, float]] = {}
    used, unused = [], []
    for index, header in enumerate(source_headers):
        field, confidence = map_header(header)
        if field and field not in {existing_field for existing_field, _ in mapped.values()}:
            mapped[index] = (field, confidence)
            used.append({"header": header, "field": field, "confidence": confidence, "column_index": index})
        else:
            unused.append({"header": header, "column_index": index, "suggestion": field, "confidence": confidence})
    records = []
    all_rows: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows[header_row + 1:], header_row + 2):
        if not any(str(cell or "").strip() for cell in row):
            continue
        cells = {str(index): (str(row[index]) if index < len(row) and row[index] is not None else "") for index in range(len(source_headers))}
        raw, headers = {}, {}
        confidence: list[float] = []
        for index, (field, score) in mapped.items():
            raw[field] = cells.get(str(index), "")
            headers[field] = source_headers[index]
            confidence.append(score)
        if raw:
            record = normalize_record(raw, headers, {**source, "row": row_number})
            record["confidence"] = round(sum(confidence) / len(confidence) * 100, 0) if confidence else 0
            record["cells_by_index"] = cells
            records.append(record)
            all_rows.append({"row_number": row_number, "cells": cells})
    if not used:
        return None
    field_set = {field for field, _ in mapped.values()}
    return {"header_row": header_row + 1, "used_columns": used, "unused_columns": unused, "records": records, "test_type": classify_table(field_set), "source_headers": source_headers, "raw_rows": all_rows}


def extract_excel(data: bytes, filename: str) -> dict[str, Any]:
    workbook = pd.ExcelFile(io.BytesIO(data))
    tables = []
    for sheet in workbook.sheet_names:
        values = pd.read_excel(io.BytesIO(data), sheet_name=sheet, header=None).fillna("").values.tolist()
        table = rows_to_table(values, {"file": filename, "sheet": sheet, "method": "excel"})
        if table:
            tables.append(table)
    return _finalize({"kind": "excel", "tables": tables}, filename)


def _extract_pdf_text(data: bytes, filename: str) -> list[dict[str, Any]]:
    """Try pdfplumber text extraction first; fall back to raw text if tables are absent."""
    import pdfplumber
    tables = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            for raw_table in page.extract_tables() or []:
                table = rows_to_table(raw_table, {"file": filename, "page": page_number, "method": "pdf-text"})
                if table:
                    tables.append(table)
    return tables


def _extract_pdf_ocr(data: bytes, filename: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Rasterize each page and run Tesseract (English + Indonesian) to recover tables from scans.
    Uses word-level bounding boxes so tabular layouts survive multi-column OCR flow."""
    from pdf2image import convert_from_bytes
    import pytesseract
    tables: list[dict[str, Any]] = []
    warnings: list[str] = []
    try:
        images = convert_from_bytes(data, dpi=250)
    except Exception as exc:
        warnings.append(f"OCR could not rasterize the PDF ({exc}). Verify the file is not corrupted.")
        return tables, warnings
    for page_number, image in enumerate(images, 1):
        try:
            words = pytesseract.image_to_data(image, lang="eng+ind", output_type=pytesseract.Output.DICT, config="--psm 6")
        except pytesseract.TesseractError as exc:
            warnings.append(f"Page {page_number}: OCR failed ({exc}).")
            continue
        rows = _words_to_rows(words)
        table = rows_to_table(rows, {"file": filename, "page": page_number, "method": "pdf-ocr"}) if rows else None
        if table:
            tables.append(table)
    if not tables and images:
        warnings.append("Scanned PDF processed with OCR but no structured table was detected. Review the file manually.")
    return tables, warnings


def _words_to_rows(data: dict[str, list], row_tolerance: int = 12, gap_ratio: float = 2.5) -> list[list[str]]:
    """Cluster Tesseract word boxes into (row, column) cells by vertical proximity and column gaps."""
    words: list[tuple[int, int, int, str]] = []
    for i in range(len(data.get("text", []))):
        text = str(data["text"][i]).strip()
        if not text:
            continue
        words.append((int(data["top"][i]), int(data["left"][i]), int(data["width"][i]), text))
    if not words:
        return []
    words.sort(key=lambda item: (item[0], item[1]))
    # Group by row via vertical proximity.
    grouped: list[list[tuple[int, int, int, str]]] = []
    for word in words:
        if grouped and abs(word[0] - grouped[-1][0][0]) <= row_tolerance:
            grouped[-1].append(word)
        else:
            grouped.append([word])
    rows: list[list[str]] = []
    for group in grouped:
        group.sort(key=lambda item: item[1])
        if len(group) < 2:
            continue
        # Split into cells wherever horizontal gap exceeds ~2.5x median char width.
        widths = [item[2] / max(1, len(item[3])) for item in group]
        median = sorted(widths)[len(widths) // 2] if widths else 8
        cells: list[str] = []
        current = group[0][3]
        prev_right = group[0][1] + group[0][2]
        for top, left, width, text in group[1:]:
            gap = left - prev_right
            if gap > median * gap_ratio:
                cells.append(current)
                current = text
            else:
                current = f"{current} {text}"
            prev_right = left + width
        cells.append(current)
        if len(cells) >= 2:
            rows.append(cells)
    return rows


def _text_to_rows(text: str) -> list[list[str]]:
    """Fallback: convert raw OCR text into row/column grid using whitespace runs."""
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        cells = [cell.strip() for cell in re.split(r"\s{2,}|\t+|\s\|\s", stripped) if cell.strip()]
        if len(cells) >= 2:
            rows.append(cells)
    return rows


def extract_pdf(data: bytes, filename: str) -> dict[str, Any]:
    warnings: list[str] = []
    tables = _extract_pdf_text(data, filename)
    if not tables:
        warnings.append("PDF has no extractable text tables; running OCR.")
        ocr_tables, ocr_warnings = _extract_pdf_ocr(data, filename)
        tables.extend(ocr_tables)
        warnings.extend(ocr_warnings)
    return _finalize({"kind": "pdf", "tables": tables, "warnings": warnings}, filename)


def _finalize(payload: dict[str, Any], filename: str) -> dict[str, Any]:
    tables = payload.get("tables", [])
    records: list[dict[str, Any]] = []
    for index, table in enumerate(tables):
        table["table_index"] = index
        for record in table["records"]:
            record["table_index"] = index
            record["assigned_test_type"] = table["test_type"]
        records.extend(table["records"])
    payload["records"] = records
    payload["detected"] = len(records)
    payload["filename"] = filename
    payload["warnings"] = payload.get("warnings", []) + ([] if tables else ["No structured table detected in the document."])
    return payload


def extract_document(data: bytes, filename: str) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return extract_excel(data, filename)
    if suffix == ".pdf":
        return extract_pdf(data, filename)
    raise ValueError("Supported files are PDF, XLSX, and XLS.")


def apply_mapping_overrides(extraction: dict[str, Any], overrides: list[dict[str, Any]]) -> dict[str, Any]:
    """Re-normalize records using user-provided column mappings and test-type overrides."""
    tables = extraction.get("tables", [])
    override_index: dict[tuple[int, int], dict[str, Any]] = {}
    type_index: dict[int, str] = {}
    for item in overrides:
        table_id = item.get("table_index")
        if table_id is None:
            continue
        if "test_type" in item and item["test_type"]:
            type_index[table_id] = item["test_type"]
        if "column_index" in item:
            override_index[(table_id, item["column_index"])] = item
    new_records: list[dict[str, Any]] = []
    for table in tables:
        idx = table["table_index"]
        if idx in type_index:
            table["test_type"] = type_index[idx]
        # Apply column-level overrides: either set/replace mapping or clear it.
        column_to_field: dict[int, str] = {item["column_index"]: item["field"] for item in table["used_columns"]}
        for (table_id, column_index), override in override_index.items():
            if table_id != idx:
                continue
            new_field = override.get("field")
            if new_field:
                column_to_field[column_index] = new_field
            else:
                column_to_field.pop(column_index, None)
        # Rebuild used/unused metadata.
        source_headers = table["source_headers"]
        used, unused = [], []
        confidence_lookup = {item["column_index"]: item["confidence"] for item in table["used_columns"]}
        for column_index, header in enumerate(source_headers):
            if column_index in column_to_field:
                field = column_to_field[column_index]
                used.append({"header": header, "field": field, "confidence": confidence_lookup.get(column_index, 1.0), "column_index": column_index, "manual": column_index not in confidence_lookup or field != next((c["field"] for c in table["used_columns"] if c["column_index"] == column_index), None)})
            else:
                suggestion, score = map_header(header)
                unused.append({"header": header, "column_index": column_index, "suggestion": suggestion, "confidence": score})
        table["used_columns"] = used
        table["unused_columns"] = unused
        # Rebuild records from stored raw rows for full re-normalization.
        rebuilt: list[dict[str, Any]] = []
        raw_rows = table.get("raw_rows", [])
        for raw_row in raw_rows:
            cells = raw_row["cells"]
            fresh_raw: dict[str, Any] = {}
            fresh_headers: dict[str, str] = {}
            for column_index, field in column_to_field.items():
                cell_value = cells.get(str(column_index)) if isinstance(cells, dict) else ""
                fresh_raw[field] = cell_value
                fresh_headers[field] = source_headers[column_index] if column_index < len(source_headers) else field
            new_record = normalize_record(fresh_raw, fresh_headers, {"file": extraction.get("filename"), "row": raw_row["row_number"]})
            new_record["cells_by_index"] = cells
            new_record["table_index"] = idx
            new_record["assigned_test_type"] = table["test_type"]
            new_record["confidence"] = 100 if any(column_to_field) else 0
            rebuilt.append(new_record)
        table["records"] = rebuilt
        new_records.extend(rebuilt)
    extraction["records"] = new_records
    extraction["detected"] = len(new_records)
    return extraction
