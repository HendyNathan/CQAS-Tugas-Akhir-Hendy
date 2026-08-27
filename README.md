# Concrete Quality Assessment System

CQAS is a full-stack quality-control workspace for concrete slump and compressive-strength test records. It is designed for a D4 Civil Engineering final project and professional review workflows.

## Current features

- Email/password registration, login, protected sessions, logout, and login lockout.
- Persistent MongoDB projects with seeded `Navapark Business Suites — DEMO DATA`.
- Manual slump and compressive-strength records with visible units.
- Excel/PDF upload validation up to 100 MB.
- Indonesian/English and mixed-language column normalization with fuzzy/OCR-spacing tolerance.
- Header-row detection, raw values, original headers, source sheet/page/row metadata, confidence, warnings, and import review.
- Deterministic assessment rules with status, reason, rule version, and timestamps.
- Duplicate and date/age anomaly warnings, plus derived strength labeling when only load and area exist.
- Responsive dashboard, mobile menu, light/dark theme persistence, PDF report download, and About/Contact.

## Structure

```text
backend/server.py       API, authentication, persistence, upload, report
backend/extraction.py   Excel/PDF extraction and bilingual field mapping
backend/analysis.py     deterministic assessment and anomaly rules
backend/uploads/        persistent original document files
frontend/src/App.js     application routes and product screens
frontend/src/App.css    centralized CQAS visual system
frontend/public/assets  replaceable logo asset
```

## Local development

Backend dependencies are in `backend/requirements.txt`. The backend binds to `0.0.0.0:8001` through supervisor and uses the existing `MONGO_URL` and `DB_NAME` values in `backend/.env`.

Frontend uses `REACT_APP_BACKEND_URL` from `frontend/.env` and is started with the existing frontend supervisor process. Do not change protected environment values.

## Environment variables

Backend requires `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and `FRONTEND_ORIGIN`. Frontend requires `REACT_APP_BACKEND_URL`. Development seed credentials are recorded in `/app/memory/test_credentials.md`.

## Extraction notes

The normalizer maps equivalent English and Indonesian fields such as `Kode`/`Sample Code`, `Tanggal Uji`/`Test Date`, `Umur (hari)`/`Age (days)`, and `Kuat Tekan MPa`/`Compressive Strength`. Unknown columns are retained in extraction review metadata rather than silently discarded. Digital PDFs use table extraction; scanned pages are reported for OCR verification in the next processing phase.

## Known limitations and next integrations

- **Google sign-in is not implemented** until OAuth client credentials and redirect settings are supplied.
- **Cloud/object storage is not implemented**; original files currently persist in `backend/uploads` with MongoDB metadata.
- Public ingress currently rewrites CORS response headers to wildcard `*` even though the backend uses an explicit credentialed origin. This must be corrected at the ingress layer before cross-origin cookie auth is production-ready.
- Project sharing, full settings editing, background OCR, and report charts are next-phase work.

## Disclaimer

This system is a digital quality-control assessment and decision-support tool. Automated assessment does not replace laboratory testing, applicable standards, project specifications, or professional engineering judgment.