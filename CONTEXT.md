# Project Overview & State

## 1. Executive Summary

- **Project Name:** Document-Validator-Model — KPITB Financial Document Verification System
- **Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL (backend), React 19 + Vite (frontend), PaddleOCR + PyMuPDF + OpenCV (OCR/CV)
- **Current Core Objective:** Main branch is now up-to-date with both Samad's doc-splitter (PR#1) and Zarghuna's bulk-queue (PR#2) merged. Local DB is fully migrated. Currently on `main`. Afsana's branch (`feature/afsana-validation-logs`) has not yet started.

## 2. Current Progress & Status

- **Current Milestone:** Post-merge integration — `main` is stable with all queued PRs landed
- **Status:** Stable — 16 preprocessing tests pass, DB migrated, demo script fixed
- **Last Updated:** 2026-08-13
- **Active branch:** `main`

## 3. Completed Tasks

### Session setup / discovery
- [x] Full read-through of the entire codebase (every backend module, full frontend, all tests, all 12 Alembic migrations, all docs) to build accurate working context
- [x] Learned project history: Antigravity ranked codebases and replaced the whole project with Zarghuna's as the base (commit `726a607`); three feature branches were created.

### Bug fixes on `feature/samad-doc-splitter` (all committed + pushed, now merged into main via PR#1)
- [x] `f989c7f` — PaddleOCR singleton reuse; removed debug logging; fixed `test_split_empty_pdf` NameError
- [x] `a69e03c` — pytest DB-hang fix in `tests/preprocessing/conftest.py`; zero-page PDF hand-craft; deprecated `use_angle_cls` → `use_textline_orientation`
- [x] `30f8737` — Fixed `httpx2` typo in requirements.txt; fixed undefined `ScanStamp` icon in `VerificationSummary.jsx`
- [x] `a876168` — Fixed `frontend/.env.example` VITE_API_BASE_URL pre-set issue
- [x] `393443c` — Added `CLAUDE.md` at project root

### Local dev environment (fully stood up and verified)
- [x] PostgreSQL 17 installed; `finance_app` role + `finance_verification` DB created
- [x] All 12 original Alembic migrations ran clean
- [x] Seeded default account (`python -m app.auth.seed`) — `EMP-1001` / `Welcome@123`
- [x] Full backend test suite (551 tests) passed — ~6m49s
- [x] Backend (:8000) and frontend (:5173) confirmed working; live login smoke test passed

### This session (2026-08-13)
- [x] Pulled `origin/main` — Zarghuna's `feature/zarghuna-bulk-queue` (PR#2) merged into main
  - 46 new/modified files, 5500+ lines: `app/bulk_queue/` module (services, workers, routes, schemas), 2 new Alembic migrations (`db1443cfdfc7` unique copy slots, `e6a1b2c3d4f5` QueueJob table), `document_analysis/fallbacks.py`, new benchmark scripts, new frontend `ProcessingProgress` component + `useProcessingProgress` hook, and a full rewrite of `preprocessing/splitter.py`
- [x] Ran `alembic upgrade head` — applied both new migrations cleanly
- [x] Fixed `demo_splitter.py`: was passing a `BinaryIO` stream to `split_bulk_pdf()` but Zarghuna's rewrite now takes `bytes` — fixed to `f.read()` before the call (committed `0f79ba7` to main)
- [x] Verified: `pytest tests/preprocessing/ -q` → **16 passed in 0.14s** (Zarghuna's new pure-PyMuPDF splitter needs no PaddleOCR at all)
- [x] Dropped our stashed `_extract_texts` OCR-parsing fix — it's now obsolete since Zarghuna's splitter does NO OCR; it's pure deterministic PyMuPDF text extraction

## 4. Current / Next Steps

- [ ] **Run `git push origin main`** to push the `demo_splitter.py` fix to GitHub
- [ ] **Run `alembic upgrade head`** on any other developer machines that haven't updated yet
- [ ] **Run the full test suite** (`pytest -q` from `backend/`) against the updated main to verify no regressions across the 500+ other tests — this takes ~6-7 minutes and requires a real local Postgres
- [ ] **Check Afsana's branch** (`feature/afsana-validation-logs`) — as of last check, no work had been started there
- [ ] **Optional: run the bulk queue worker** — see "Run Commands" below for how to start it as a background process
- [ ] **Investigate rule engine coverage gaps** (deferred, not urgent): see §6 Known Issues

## 5. Key Decisions & Technical Context

- **GitHub repo:** `https://github.com/abdulsamad-codes/Document-Validator-Model` (Abdul Samad's account)
- **Branch strategy:** `main` (stable, all PRs merged) ← `feature/afsana-validation-logs` (pending, no work yet). `feature/samad-doc-splitter` and `feature/zarghuna-bulk-queue` are fully merged.
- **Local dev DB credentials** (must match `backend/.env`): role `finance_app` / `change-me`, database `finance_verification`, `localhost:5432`. Default login: `EMP-1001` / `Welcome@123`.

### Run Commands
```bash
# Backend (from backend/)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (from frontend/)
npm run dev

# Bulk queue worker (optional background process — from backend/)
python -m app.bulk_queue

# Tests
pytest tests/preprocessing/ -q          # DB-free, ~0.1s
pytest -q                               # full suite ~6-7min, needs real Postgres

# Migrations
alembic upgrade head                    # run after pulling new migrations
```

### Key Architecture Changes in Zarghuna's PR#2
- **`app/bulk_queue/`** — new module: `services.py` (job enqueueing), `workers.py` (threaded workers with heartbeat + `FOR UPDATE SKIP LOCKED` claiming), `routes.py` (submit/status/cancel endpoints), `__main__.py` (dedicated worker process mode)
- **`preprocessing/splitter.py`** — COMPLETELY REWRITTEN: now pure PyMuPDF, zero OCR/PaddleOCR, deterministic header-zone phrase matching with strong/weak evidence distinction, CNIC front/back discrimination, `split_bulk_pdf(bytes)` signature (was `BinaryIO`)
- **`document_analysis/fallbacks.py`** — new safe fallbacks for analysis when OCR produces no data
- **`database/models/queue_job.py`** + **`queue_job_repository.py`** — new QueueJob persistence layer
- **`VITE_API_BASE_URL` must stay commented out** in `frontend/.env` for local dev — CORS-free, Vite proxies `/api/v1`

## 6. Active Blockers & Known Issues

- Rule engine (`backend/app/rule_engine/rules/*.py`) has known coverage gaps against `docs/Master_Rules_Combined.md`: no blank-date enforcement, no PayMin/Digital Muhasil terminology check, no branch-name cross-document consistency, no organization-name consistency, no per-page 1-Link signature check, no E-Stamp/Notary visual authentication, no CNIC expiry check.
- `Settings → Administration` in the frontend is marked "Restricted" but has no actual RBAC — cosmetic only.
- No linter configured for either backend or frontend.
- Full 500+ test suite requires a real local Postgres — see `CLAUDE.md` for setup recipe.
- `feature/afsana-validation-logs` branch exists on GitHub but has no commits yet.
