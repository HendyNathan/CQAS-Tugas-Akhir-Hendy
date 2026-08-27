"""PDF report generation with EN/ID language support and configurable unit display."""
import io
from datetime import datetime
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from units import UNIT_LABELS, convert_for_display


REPORT_TEXT = {
    "en": {
        "title": "CONCRETE QUALITY ASSESSMENT REPORT",
        "project": "Project",
        "generated": "Generated",
        "records": "Total records",
        "criteria": "Assessment criteria",
        "target_slump": "Target slump",
        "min_slump": "Minimum slump",
        "max_slump": "Maximum slump",
        "design_strength": "Design compressive strength",
        "not_set": "Not set",
        "disclaimer": "This report is a decision-support tool and does not replace laboratory testing, applicable standards, or professional engineering judgment.",
        "sectionStrength": "COMPRESSIVE STRENGTH",
        "sectionSlump": "SLUMP",
        "colSample": "Sample",
        "colDate": "Test date",
        "colAge": "Age",
        "colResult": "Result",
        "colStatus": "Status",
        "colReason": "Reason / recommendation",
        "colTarget": "Target",
        "footer": "Concrete Quality Assessment System | Developed by Nathan | D4 Civil Engineering",
        "noRecords": "No records available.",
        "days": "days",
        "status": {
            "COMPLIANT": "Compliant",
            "WARNING": "Warning",
            "NON-COMPLIANT": "Non-compliant",
            "INSUFFICIENT DATA": "Insufficient data",
            "UNASSESSED": "Unassessed",
        },
        "rules": {
            "slump.actual.required": "Actual slump is missing.",
            "slump.minimum": "Actual slump is below the configured minimum acceptance limit.",
            "slump.maximum": "Actual slump is above the configured maximum acceptance limit.",
            "slump.target.missing": "Target slump is missing; verify against project criteria.",
            "slump.range": "Actual slump is within the configured acceptance criteria.",
            "strength.actual.required": "Compressive strength is missing.",
            "strength.planned.missing": "Design strength is missing; verify against project criteria.",
            "strength.design.low": "Actual strength is below the design value and requires verification.",
            "strength.design.ok": "Actual strength meets or exceeds the design value.",
        },
    },
    "id": {
        "title": "LAPORAN PENILAIAN KUALITAS BETON",
        "project": "Proyek",
        "generated": "Dibuat",
        "records": "Total catatan",
        "criteria": "Kriteria penilaian",
        "target_slump": "Slump rencana",
        "min_slump": "Slump minimum",
        "max_slump": "Slump maksimum",
        "design_strength": "Kuat tekan rencana",
        "not_set": "Belum diatur",
        "disclaimer": "Laporan ini adalah alat pendukung keputusan dan tidak menggantikan pengujian laboratorium, standar yang berlaku, atau pertimbangan profesional insinyur.",
        "sectionStrength": "KUAT TEKAN",
        "sectionSlump": "SLUMP",
        "colSample": "Sampel",
        "colDate": "Tanggal uji",
        "colAge": "Umur",
        "colResult": "Hasil",
        "colStatus": "Status",
        "colReason": "Alasan / rekomendasi",
        "colTarget": "Rencana",
        "footer": "Sistem Penilaian Kualitas Beton | Dikembangkan oleh Nathan | D4 Teknik Sipil",
        "noRecords": "Tidak ada catatan tersedia.",
        "days": "hari",
        "status": {
            "COMPLIANT": "Memenuhi",
            "WARNING": "Peringatan",
            "NON-COMPLIANT": "Tidak memenuhi",
            "INSUFFICIENT DATA": "Data tidak lengkap",
            "UNASSESSED": "Belum dinilai",
        },
        "rules": {
            "slump.actual.required": "Nilai slump aktual tidak tersedia.",
            "slump.minimum": "Slump aktual di bawah batas penerimaan minimum yang dikonfigurasi.",
            "slump.maximum": "Slump aktual di atas batas penerimaan maksimum yang dikonfigurasi.",
            "slump.target.missing": "Slump rencana tidak tersedia; verifikasi terhadap kriteria proyek.",
            "slump.range": "Slump aktual berada di dalam kriteria penerimaan yang dikonfigurasi.",
            "strength.actual.required": "Nilai kuat tekan tidak tersedia.",
            "strength.planned.missing": "Kuat tekan rencana tidak tersedia; verifikasi terhadap kriteria proyek.",
            "strength.design.low": "Kuat tekan aktual di bawah nilai rencana dan memerlukan verifikasi.",
            "strength.design.ok": "Kuat tekan aktual memenuhi atau melebihi nilai rencana.",
        },
    },
}


def _reason(rule: str | None, status: str, texts: dict) -> str:
    if not rule:
        return ""
    key = rule
    if rule == "strength.design":
        key = "strength.design.ok" if status == "COMPLIANT" else "strength.design.low"
    return texts["rules"].get(key, "")


def _line(pdf: canvas.Canvas, x: float, y: float, text: str) -> None:
    pdf.drawString(x, y, text)


def _new_page(pdf: canvas.Canvas) -> float:
    pdf.showPage()
    pdf.setFillColorRGB(0.08, 0.1, 0.14)
    pdf.setFont("Helvetica", 10)
    return 790


def build_report(project: dict, records: list[dict], lang: str = "en") -> bytes:
    texts = REPORT_TEXT.get(lang, REPORT_TEXT["en"])
    settings = project.get("settings") or {}
    strength_records = [r for r in records if r["test_type"] == "strength"]
    slump_records = [r for r in records if r["test_type"] == "slump"]
    slump_unit = settings.get("slump_unit", "mm")
    strength_unit = settings.get("strength_unit", "MPa")

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(texts["title"])
    pdf.setFillColorRGB(0.85, 0.35, 0.02)
    pdf.setFont("Helvetica-Bold", 20)
    _line(pdf, 48, 790, texts["title"])
    pdf.setFillColorRGB(0.08, 0.1, 0.14)
    pdf.setFont("Helvetica", 11)
    y = 755
    header_lines = [
        f"{texts['project']}: {project['name']} ({project.get('code', '')})",
        f"{texts['generated']}: {datetime.now().strftime('%d %B %Y')}",
        f"{texts['records']}: {len(records)}",
    ]
    for line in header_lines:
        _line(pdf, 48, y, line); y -= 18

    pdf.setFont("Helvetica-Bold", 11); _line(pdf, 48, y, texts["criteria"]); y -= 16
    pdf.setFont("Helvetica", 10)
    for label, value, unit in [
        (texts["target_slump"], settings.get("target_slump"), slump_unit),
        (texts["min_slump"], settings.get("min_slump"), slump_unit),
        (texts["max_slump"], settings.get("max_slump"), slump_unit),
        (texts["design_strength"], settings.get("design_strength"), strength_unit),
    ]:
        if value is None:
            _line(pdf, 60, y, f"{label}: {texts['not_set']}")
        else:
            _line(pdf, 60, y, f"{label}: {value} {UNIT_LABELS.get(unit, unit)}")
        y -= 14

    y -= 4
    pdf.setFont("Helvetica-Oblique", 9); _line(pdf, 48, y, texts["disclaimer"]); y -= 22

    for section_key, section_records, section_unit_pref, canonical_unit in [
        ("sectionStrength", strength_records, strength_unit, "MPa"),
        ("sectionSlump", slump_records, slump_unit, "mm"),
    ]:
        if y < 120:
            y = _new_page(pdf)
        pdf.setFillColorRGB(0.85, 0.35, 0.02); pdf.setFont("Helvetica-Bold", 12)
        _line(pdf, 48, y, f"{texts[section_key]}  ·  {len(section_records)}"); y -= 16
        pdf.setFillColorRGB(0.08, 0.1, 0.14); pdf.setFont("Helvetica-Bold", 9)
        _line(pdf, 48, y, texts["colSample"])
        _line(pdf, 130, y, texts["colDate"])
        _line(pdf, 205, y, texts["colAge"])
        _line(pdf, 245, y, texts["colResult"])
        _line(pdf, 325, y, texts["colStatus"])
        _line(pdf, 415, y, texts["colReason"])
        y -= 12
        pdf.setFont("Helvetica", 9)
        if not section_records:
            _line(pdf, 60, y, texts["noRecords"]); y -= 14; continue
        for record in section_records:
            row = record["record"]
            sample = row.get("sample_code") or row.get("record_number") or "-"
            date = row.get("test_date") or "-"
            age = f"{row.get('age_days', '-')} {texts['days']}" if section_key == "sectionStrength" else "-"
            raw_value = row.get("compressive_strength") or row.get("derived_strength") if section_key == "sectionStrength" else row.get("actual_slump")
            display_value, display_unit = convert_for_display(raw_value, canonical_unit, section_unit_pref)
            result = f"{display_value:g} {UNIT_LABELS.get(display_unit, display_unit)}" if display_value is not None else "-"
            assessment = row.get("assessment", {})
            status = texts["status"].get(assessment.get("status") or "UNASSESSED", "-")
            reason = _reason(assessment.get("rule"), assessment.get("status", ""), texts)
            _line(pdf, 48, y, str(sample)[:14])
            _line(pdf, 130, y, str(date)[:12])
            _line(pdf, 205, y, str(age)[:8])
            _line(pdf, 245, y, result[:14])
            _line(pdf, 325, y, status[:16])
            for chunk_index, chunk_start in enumerate(range(0, min(len(reason), 240), 60)):
                _line(pdf, 415, y - chunk_index * 10, reason[chunk_start:chunk_start + 60])
            y -= max(14, ((min(len(reason), 240) + 59) // 60) * 10 + 4)
            if y < 90:
                y = _new_page(pdf)
        y -= 12

    pdf.setFont("Helvetica-Oblique", 8)
    _line(pdf, 48, 30, texts["footer"])
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()
