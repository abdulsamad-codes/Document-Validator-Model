# Project Context – FinTech Document Verification System

Last updated: 2026-08-13. This file is the single source of truth for project state across sessions/tools — keep it current rather than trusting an earlier assistant summary in chat history.

## What this project is

A full-stack system for banks/KPITB to onboard merchants: upload financial onboarding documents, run them through OCR → field extraction → confidence scoring → normalization → a business-rule engine → human review, and curate corrected data into a versioned dataset for continuous learning. Backend: FastAPI + PostgreSQL (SQLAlchemy 2 + Alembic). Frontend: React 19 + Vite.

## Current state: everything merged to `main`, test suite green, Operator Dashboard shipped

Three teammates' branches (`feature/samad-doc-splitter`, `feature/zarghuna-bulk-queue`, `feature/afsana-validation-logs`) are all merged into `main`. Work happens directly on `main`.

**Backend test suite: 704 passed, 0 failed** (`cd backend && .venv/Scripts/pytest.exe -q`, ~4 min). Re-run this yourself before trusting the number if it's been a while.

### What each branch shipped
- **Samad**: original bulk PDF splitter + CV preprocessing + bulk-upload endpoint (later superseded by the async redesign below).
- **Zarghuna**: async bulk upload — `upload_bulk` stores the raw PDF as a `BULK_UPLOAD`-typed placeholder `Document` and enqueues it on a Postgres-backed job queue (`app/bulk_queue/`, `FOR UPDATE SKIP LOCKED` claiming). A background `BulkQueueWorker` later splits/classifies pages (`DocumentSplitter.split_bulk_pdf`, PaddleOCR fallback for scanned pages) — this fixed the original synchronous-splitter HTTP timeout on large/scanned bulk uploads.
- **Afsana**: the `validation` module — `ValidationTask`/`ValidationRun`/`ValidationLog` models plus a full API (`app/validation/routes.py`): task lifecycle (create/start/complete/reject/request-correction), stored check results, immutable audit log, review-time field/evidence logging. This is the backend half of the human-review workflow.

### 2026-08-13 stabilization session (this session)

A prior session (different tool) had merged everything but left the suite at "89 failing tests, never root-caused," and had introduced a rule-registry regression while trying to fix an unrelated test. This session found and fixed the real causes:

- **Missing migration**: `DocumentType.BULK_UPLOAD` existed in Python but was never added to the Postgres enum — every bulk upload failed. Added `alembic/versions/02ffa030b9e1_add_bulk_upload_document_type.py`.
- **Wrong repository method call**: `upload_bulk` called a nonexistent `QueueJobRepository.enqueue()`; fixed to call the real `enqueue_uploaded_documents(...)`, removed a dead import, rewrote the stale docstring.
- **Real atomicity bug**: `DocumentRepository.create()` commits immediately, so a failure in the enqueue step right after couldn't be rolled back — fixed with an explicit compensating delete.
- **Added `DocumentSplitter.validate_structure()`**: a cheap synchronous readable/non-zero-page check so garbage uploads get an immediate 400 instead of silently queuing.
- **Rule registry regression fixed**: `CrossBranchCodeRule`/`FormatEStampRule` were imported but never registered, and `VisualStampTripartiteRule`/`VisualStampAmcRule` were actively disabled — all to force the rule count to stay at a stale "47" instead of fixing a real duplicate-registration bug. Restored `FormatEStampRule` and the two visual stamp rules (registry is now **50 rules**). **Deliberately did not restore `CrossBranchCodeRule`** — see "Known gaps" below.
- **Real bug in `date_rules.py`**: the new date-presence rules' PASS branch crashed (`AttributeError`) because it treated a `list[str]` as `FieldValue` objects. Fixed and de-duplicated into `_DateRule._evaluate_presence()`.
- Rewrote `test_date_blank_rules.py` (was testing against a broken hand-rolled `RuleContext` double that was never actually exercised) and several other tests that had hardcoded rule counts or premises contradicting real service-layer rules (e.g. "only one active task per application" is enforced by design, not a bug).
- **Fixed genuine Windows flakiness** in `test_bulk_queue.py::test_multiple_worker_processes_claim_disjoint_jobs`: 3 subprocess workers appended to one shared file, which isn't reliably atomic across OS processes on Windows. Fixed by giving each worker its own file and merging in the test. Verified stable across 15+ repeated runs.

### New this session: Operator Dashboard (frontend)

`/human-review` (nav slot already existed, was an unrouted placeholder) now has a real page: `frontend/src/pages/OperatorDashboard/OperatorDashboardPage.jsx`. Queue table + inline review panel driving the validation task lifecycle (start / complete / reject / request-correction) against Afsana's API, with stored check results and the audit log shown per task. New files: `services/validation.js`, `hooks/useValidationTasks.js` + `useValidationTask.js`, `components/validation/*`, `VALIDATION_TASK_STATUSES` in `data/statuses.js`. Follows existing conventions (CSS Modules, manual `useState`/`useEffect`, no new state library). `npm run build` passes clean. **Browser-verified end-to-end** with Playwright (login as `temp`/`1234` → create task via API → Start Review → Reject with reason → confirmed status/audit-log updates in the UI at every step).

## Known gaps (verified 2026-08-13, don't re-discover from scratch)

**Rule engine coverage vs. `docs/Master_Rules_Combined.md`** — no automated coverage for: blank-date enforcement on Tripartite/Bilateral preambles, PayMin/Digital Muhasil/Paymere BCX terminology matching, organization-name consistency across documents, per-page 1-Link signature requirement, document layout/point-numbering conformance, E-Stamp visual authentication, Notary Public stamp detection, Formal Request Letter subject-line check, CNIC expiry/completeness. (Schedule-of-Charges/BRD signature+stamp checks are deliberately handled via the human-verification manual checklist instead.) **None of these fields have any extraction/normalization support in the codebase today** — confirmed by grep. Do not add a rule for any of them without adding real extraction first: see the `CrossBranchCodeRule` incident above for exactly what goes wrong otherwise (`_CrossDocumentRule` hard-`FAIL`s on a missing field; `_FormatRule` only WARNs; `_VisualRule` degrades to `PENDING_MANUAL_REVIEW` — know which base class before wiring a new rule in).

**Two independent `CRITICAL_FIELDS` lists** (`document_analysis/constants.py`, per-document-type dict, vs `confidence/constants.py`, flat global set) are deliberately different shapes for different purposes — not a bug, now documented in-code.

**Dead-looking but intentionally-kept code**: `DatasetValidationError`, `InvalidReportRequest` — defined, exported, documented in `docs/` as part of their module's exception contract, never raised. Left alone rather than deleted.

## What's actually left to build

1. **Extraction support for the rule-engine gaps above**, if those checks are wanted — this is the real remaining scope, not UI work.
2. **Human Verification workspace for field-level corrections** — the Operator Dashboard drives the *task* lifecycle and shows results/logs, but the per-field verify/correct endpoints (`POST /validation/fields/{id}/verify|correct`) aren't wired into the UI yet (no field-level review widget). Worth adding once there's a real application with extracted fields to review against.
3. Whatever the team prioritizes next — the backend and this new frontend page are both stable and tested; there's no "broken foundation" blocking further work anymore.

---

*Update this file at the end of any session that changes what's true about the project — a stale context.md is worse than none, since the next session (any tool) will trust it.*
