# Concrete Quality Assessment System — Product Record

## Original problem statement

Build a complete full-stack Concrete Quality Assessment System for D4 Civil Engineering. It must support concrete slump and compressive-strength assessment, persistent projects and documents, Indonesian/English extraction, OCR-tolerant normalization, import review, unit-aware analysis, PDF reports, authentication, sharing, responsive UI, theme persistence, replaceable branding, and clearly labeled Navapark demo data.

## Architecture decisions

- React 19 + React Router + Recharts provide the responsive workspace and charts.
- FastAPI on port 8001 provides protected API routes and deterministic assessment services.
- MongoDB uses application UUIDs for users, projects, records, and documents; raw extraction metadata is preserved inside records.
- `extraction.py` owns bilingual/fuzzy header mapping, header-row detection, dates, numbers, units, and source traceability.
- `analysis.py` owns transparent status rules, reasons, warnings, duplicate detection, and derived strength labeling.
- Uploaded source files are retained in persistent server storage under `backend/uploads`; cloud object storage remains a P1 integration.
- `/public/assets/logo.svg` is centralized and replaceable without changing component logic.

## Users and personas

- Civil engineering student reviewing a final-project dataset.
- Site/laboratory quality-control engineer importing mixed-language reports.
- Project owner sharing verified results with an editor or viewer.

## Core requirements and implementation status

- Authentication, protected sessions, registration, logout, seeded owner: implemented.
- Projects, manual slump/strength records, deterministic analysis: implemented.
- Indonesian/English Excel extraction, fuzzy mapping, raw/source preservation, import review API: implemented.
- Digital PDF table extraction and 100 MB validation: implemented.
- Responsive dashboard, mobile navigation, light/dark theme, demo data: implemented.
- PDF report endpoint, contact/about, engineering disclaimer: implemented.
- Google sign-in: P1, not implemented because provider credentials/configuration were not supplied.
- Cloud/object storage: P1, not implemented; persistent local storage is active.
- Project sharing and full settings editor: P1.
- Scanned-PDF OCR background processing: P1; current digital PDF extractor explicitly flags OCR verification.

## Change log

- 2026-08-27: Replaced starter app with CQAS full-stack foundation, extraction engine, analysis rules, report generation, auth, project UI, demo data, responsive theme, and test coverage.
- 2026-08-27: Fixed UUID session lookup, current-user serialization, and ProjectDetail async-effect crash.
- 2026-08-27: Added Mongo-backed five-failure/15-minute login lockout and explicit frontend CORS configuration.

## Prioritized backlog

### P0 remaining

- Resolve public ingress CORS rewriting `Access-Control-Allow-Origin` to `*` while credentialed sessions are used.
- Add provider-backed Google OAuth after project credentials and redirect configuration are supplied.

### P1 remaining

- Add cloud/object storage adapter and background processing queue for large/OCR uploads.
- Add project sharing links with OWNER/EDITOR/VIEWER backend authorization.
- Add editable criteria and unit preferences UI.
- Add scanned PDF OCR and multi-page table consolidation.

### P2 remaining

- Expand chart filtering and supplier comparisons.
- Add report charts, logo upload, and richer report traceability pages.
- Add saved mapping templates and additional engineering standards references.