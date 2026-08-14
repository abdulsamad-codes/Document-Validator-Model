# Project Context – FinTech Document Verification System

Last updated: 2026-08-13. This file is the single source of truth for project state across sessions/tools — keep it current rather than trusting an earlier assistant summary in chat history.

## What this project is

A full-stack system for banks/KPITB to onboard merchants: upload financial onboarding documents, run them through OCR → field extraction → confidence scoring → normalization → a business-rule engine → human review, and curate corrected data into a versioned dataset for continuous learning. Backend: FastAPI + PostgreSQL (SQLAlchemy 2 + Alembic). Frontend: React 19 + Vite.

**⚠️ The GitHub repo (`abdulsamad-codes/Document-Validator-Model`) is public.** Real onboarding documents (real IBANs, CNICs, officer names) belong in `Confidential Data/` at the project root, which is gitignored — never loose in the repo. On 2026-08-13 a real onboarding PDF was found committed and pushed un-ignored (fixed by untracking + gitignoring it, commit `bc57cff`); git history was deliberately left as-is rather than rewritten, so that one file is still recoverable from an old commit if anyone goes looking. See `Confidential Data/` for the ~19 real documents already handled correctly.

**⚠️ Never run `pytest` while real data is loaded in the dev database.** `tests/conftest.py`'s autouse `isolated_database` fixture runs `DELETE FROM applications` (cascading to documents/queue_jobs) before AND after **every single test**, against whatever database `SessionLocal`/`DATABASE_URL` points at — which locally is the same Postgres database the running backend and queue worker use. On 2026-08-13 this wiped a real uploaded application while it was mid-processing (see below). Before running the suite locally, check the `applications` table is empty first, or point `DATABASE_URL` at a separate test database.

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

### 2026-08-13, later same day: second `.enqueue()` bug + a data-loss incident

While helping the user check on a real document they'd uploaded through the running app, found a **second instance** of the same nonexistent-method bug fixed earlier in `upload/services.py` — this one in `document_processing/services.py::_process_bulk_upload()`, which called `QueueJobRepository.enqueue()` (doesn't exist) instead of `enqueue_uploaded_documents(...)`. Effect: bulk uploads split into per-document records successfully, but those documents were never enqueued for OCR/extraction — the pipeline silently stalled forever with no error surfaced anywhere. Fixed in commit `7f3129d`, with a regression test (`test_bulk_upload_split_documents_are_enqueued_for_processing` in `test_bulk_queue.py`) asserting split documents get queue jobs.

**While verifying that fix, running the new regression test wiped the user's real in-progress application** — see the `isolated_database` warning above. The application, its documents, and its queue job were permanently deleted (hard `DELETE`, no soft-delete/backup). The `users` table was unaffected in that instance (temp account still worked), but don't assume that generalizes — treat any pytest run against a database holding real data as destructive to all of `applications`/`documents`/`queue_jobs`/`users`.

**A third, deeper bug in the same area, fixed same day (commit `36bf456`)**: even with the enqueue bug fixed, every bulk-split document was still guaranteed to fail permanently. `process_one()` correctly refuses to OCR/extract a document without a stored PASS technical-validation report (`document_processing/services.py:214`), but the bulk-split path (`_process_bulk_upload`) never ran technical validation on the documents it created before enqueueing them for that exact processing — the queue worker treats a "skipped, not validated" outcome as a job failure and retries it into permanent `FAILED` status (`app/bulk_queue/workers.py:196-199`). Fixed by calling `TechnicalValidationService(self._db).validate(application_id=application_id)` right after `create_many()` and before `enqueue_uploaded_documents()`, mirroring what the manual (non-bulk) upload flow already does via its own separate `POST .../technical-validation/validate` call. A real application (`#2757`) hit this and burned all its retries — unrecoverable, user had to re-upload.

### 2026-08-14: two more bugs found watching a real 21-page bulk upload process end-to-end (commit `a8c41bf`)

With the three bugs above fixed, a real bulk upload (application `#2758`, a 21-page scanned PDF) was watched through the full pipeline live. It split correctly into 3 documents (Tripartite Agreement, Authority Letter, CNIC Front) and passed technical validation, but hit two more real bugs:

- **`ProcessingMethod.OCR` doesn't exist** (`document_processing/services.py`, `_process_bulk_upload`'s success return) — real member is `PADDLE_OCR`. This crashed *after* the split had already fully succeeded, so the split job was wrongly marked failed and scheduled to redo the entire multi-minute OCR pass on retry (which would then hit the `MAX_COPIES` duplicate guard from the bug above and fail again). Fixed.
- **`PROCESSING_TIMEOUT_SECONDS` was `60.0`** (`document_processing/constants.py`) — but PaddleOCR fallback on this CPU-only machine measured **90–150 seconds per page** in this same session. Any multi-page scanned document (e.g. the 2-page Authority Letter) was mathematically guaranteed to time out. Raised to `600.0`. **If OCR is ever run on a machine without a GPU, re-measure per-page time and adjust this constant** — it's a flat per-document budget, not scaled to page count, so a document with many more pages than this session's test case could still need a higher value.

Verified via a static AST sweep (parse every `.py` file under `app/`, cross-reference every `EnumClass.MEMBER` attribute access against the enum's real `__members__`) that no other enum reference in the codebase points at a nonexistent member, and that every repository method called from `document_processing/services.py` actually exists on its class (including inherited `BaseRepository` methods). Worth re-running this sweep after any future change that references enum members by name.

**Known but not fixed, lower priority**: `_process_claimed_job` in `app/bulk_queue/workers.py` treats a `SKIPPED` processing outcome (e.g. "document did not pass technical validation") identically to a real failure — it retries up to `max_attempts` times even though a technical-validation verdict won't change between retries, wasting time before landing on permanent `FAILED`. Also, running two dev processes (uvicorn + the bulk queue worker) against the same `logs/backend.log` causes harmless but noisy `PermissionError` spam on Windows log rotation (`os.rename` can't rotate a file another process has open) — doesn't affect correctness, just clutters the log.

**Unresolved as of end of 2026-08-14 session**: application `#2758`'s bookkeeping is slightly inconsistent — queue job `#4905` (the split job) and `#4907` (Authority Letter's OCR job) were mid-retry when their worker processes were killed to stop a wasteful redo, so they're stuck showing `PROCESSING` in the DB even though no worker is running. The actual documents/data are fine (3 real documents exist, technically validated). A direct SQL fix was attempted but blocked by an automated command-safety classifier that doesn't respond to in-chat approval (only an actual permission-prompt grant, e.g. via Claude Code's Bash permission settings, would unblock it). **Next session: either grant that permission and run the fix, or just start the queue worker again — `recover_stale_processing` will eventually reclaim both jobs on its own (safe, just means Authority Letter's OCR and the (unnecessary) split job both redo one more time before settling).**

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
