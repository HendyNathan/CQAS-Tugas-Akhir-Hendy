# Concrete Quality Assessment System (CQAS) - PRD

## Original Problem Statement
Build a full-stack "Concrete Quality Assessment System" for D4 Civil Engineering, capable of processing concrete Slump Test and Compressive Strength Test lab reports (PDF, XLSX, XLS) with robust Indonesian/English column mapping, OCR for scanned PDFs, deterministic assessment, anomaly detection, sharing, and PDF report generation.

## Architecture
- Frontend: React 19 + Tailwind/Shadcn + Recharts + react-router-dom
- Backend: FastAPI + Motor (MongoDB) + pdfplumber + PyMuPDF + pytesseract + pdf2image + ReportLab
- Storage: Emergent Object Storage (durable) with local disk fallback
- Auth: JWT (email+password) + Emergent Google OAuth (dual login)
- OCR: Tesseract (eng+ind) with word-box column reconstruction

## User Personas
- QA/QC Engineer: uploads lab reports, reviews mapping, generates reports
- Project Owner: manages members, shares evidence
- Consultant (Viewer): reads shared evidence

## Implemented (Iteration 2 - 2026-02-27)
- Dual login (email/password + Emergent Google OAuth) with httpOnly cookies
- Emergent Object Storage integration (with local fallback)
- Robust extraction engine:
  - Excel + PDF text + scanned PDF (OCR word-box columns)
  - Indonesian/English fuzzy header mapping (17 canonical fields)
  - Multi-table detection with automatic Slump vs Strength classification
  - Manual column mapping override with `apply_mapping_overrides`
  - Test-type override per table
  - Raw values preserved for traceability
- Import Review UI with:
  - Per-table test type selector
  - Column mapping edit/remove
  - Add mapping to unmapped columns
  - Live preview of remapped records
- PART 55 acceptance test passes end-to-end
- Persisted assessment via `/analyze` writes back into records
- Document history strip on project detail

## PART 55 Acceptance Test
Excel headers `No | Kode | Tanggal Cor | Tanggal Uji | Umur (hari) | Luas Penampang (cm²) | Berat (kg) | Beban (kN) | Kuat Tekan MPa (N/mm²) | Pola Retak | Keterangan` are mapped correctly and 100% detected.

## Backlog (P1/P2)
- P2: App.js/ProjectDetail modularization into /pages and /components/features
- P2: Saved mapping templates per user for recurring lab formats
- P2: Dynamic user-uploaded logo replacement flow
- P2: Configurable engineering limits UI inside Project Settings
- P2: Report enhancements (charts, per-supplier tables)
- P2: Multi-record extraction from mixed-domain single PDF (Slump + Strength side by side)

## Test Credentials
Email: `admin@cqas.local` / Password: `admin123` (Owner of demo project NBS-DEMO)
