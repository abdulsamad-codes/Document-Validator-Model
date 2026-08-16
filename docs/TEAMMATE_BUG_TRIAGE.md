# Teammate Bug Triage — 2026-08-16

A teammate ran a broad review of the app (frontend + backend, not scoped to today's
Phase 1 work) and reported 32 distinct issues in three batches: a frontend build
issue, six standalone UI/pipeline complaints, a 25-item Critical/High/Medium/Low
severity list, and a root-cause chain for "uploaded documents never get processed."

Every item below was independently verified against the current codebase (read-only,
no fixes applied as part of this triage). **Corrected tally: 28 CONFIRMED, 4 FALSE,
0 unverifiable, out of 32 total.**

**Correction (2026-08-17, second pass)**: Critical #1 ("missing auth on 40+
endpoints") was originally marked CONFIRMED in this file's first pass, based on
grepping each route file individually for `_CURRENT_USER` usage. That grep missed
`backend/app/api/__init__.py`, which wraps every one of the flagged routers —
`technical_validation`, `completeness`, `reports`, `document_processing`,
`document_analysis`, `rule_engine`, `feedback`, `continuous_learning`,
`normalization`, `validation`, `confidence`, and `upload` — in a single
`protected_router = APIRouter(dependencies=[Depends(get_current_user)])`, applied
router-wide on 2026-08-14 (see `backend/tests/test_auth_enforcement.py`, the
dedicated regression test for this exact gap). Ran that test directly:
`test_protected_endpoint_inventory_has_53_entries`,
`test_unauthenticated_requests_rejected_everywhere`, and
`test_health_and_auth_remain_reachable_without_a_session` all pass — all 53
protected endpoints reject unauthenticated requests with 401 today, no code
changes needed. The per-route `_CURRENT_USER` usage this triage found in
`upload/routes.py`, `confidence/routes.py`, and `human_verification/routes.py`
isn't the auth gate at all — those specific handlers pull `current_user.name` for
business data (`created_by`, `reviewer_name`), on top of auth already enforced
globally. Moved to FALSE below; tally corrected from 29/3 to 28/4.

**2 of the 28 confirmed bugs have since been fixed** (the `react-error-boundary`
devDependency item under "Frontend build" and the `autoStartProcessingAfterUpload`
default under "Root cause: uploaded documents never get processed" — both marked
below), by commit `91307f8` on `feature/zarghuna-bulk-queue`, merged to `main` via
PR #6. The remaining 26 have not been fixed yet — this file is a record of what was
found, not a changelog of what was done. See "Suggested fix order" at the bottom for
a proposed starting point, pending an explicit scope decision on when to pick this up.

No real PII or `Confidential Data/` content appears anywhere in this file — every
finding below is a pure code/file:line reference.

## FALSE (4)

**`queue_jobs.job_type` missing migration** — reported as: uploading a file gives a
500 because the `queue_jobs.job_type` column doesn't exist, and the fix is to run
`alembic upgrade head`. Checked directly against the live dev DB used for tonight's
demo: the column exists (`queue_jobs` columns include `job_type`) and `alembic
current` / `alembic heads` both report `e1f2a3b4c5d6 (head)` — fully migrated. This
environment's DB is not affected; almost certainly the teammate's own local DB was
out of sync (migration never applied there), not a codebase bug.

**"Authority Letter copy 1 contains the full PDF, not just the authority letter
page"** — for `Conservator Wildlife Peshawar Zoo.pdf` viewed in the application's
document list. `backend/app/upload/services.py` `upload()` (single-document upload,
lines 109-178) stores the file exactly as given, under whatever `document_type` the
caller sends in the form field — it never splits anything. Only `upload_bulk()`
(lines 180-274) triggers `DocumentSplitter`. If a user uploads a whole combined PDF
through the single-document path and tags it "Authority Letter," the whole file
becomes that document by design. Not a splitter defect.

**Processing sidebar count mismatch** ("1 waiting / 0 processing / 0 attention" vs.
a total of 2 shown elsewhere) — `backend/app/bulk_queue/services.py:101-117`
(`processing_progress`) computes `total_documents` as the sum of *all* job statuses
including `COMPLETED`, while `frontend/src/components/processing/ProcessingProgress/
ProcessingProgress.jsx:64-69` intentionally shows only queued/processing/attention
(completed is shown separately — see `ProcessingProgress.jsx:40` and
`frontend/src/pages/Processing/ProcessingPage.jsx:163-167`). Both UI pieces read the
same backend numbers consistently; a completed document not appearing in the
three-part breakdown is by design, not a data bug.

**"Missing auth on 40+ endpoints"** — moved here from CONFIRMED, see the
correction note at the top of this file. `backend/app/api/__init__.py` wraps every
flagged router in `protected_router = APIRouter(dependencies=
[Depends(get_current_user)])`, applied globally on 2026-08-14.
`backend/tests/test_auth_enforcement.py` (3 tests) empirically confirms all 53
protected endpoints reject unauthenticated requests with 401 right now. Not a bug.

## CONFIRMED (28)

### Frontend build

- **`react-error-boundary` in `devDependencies`, used in production** —
  `frontend/package.json:31` lists it under `devDependencies`; imported at
  `frontend/src/components/common/ErrorBoundary/ErrorBoundary.jsx:2`, which wraps
  the entire app at `frontend/src/main.jsx:11` (the root render call). Vite won't
  bundle it in a production build. Fix: move to `dependencies`, reinstall.
  **Fixed by `91307f8`** — moved to `dependencies` in both `package.json` and
  `package-lock.json`. Confirmed by reading the diff directly, not assumed from
  the commit title.

### UI / pipeline complaints

- **New document's name doesn't appear in the application list (shows "—")** —
  real bug, but frontend cache staleness, not a backend bug. Backend correctly sets
  `application.name` on first upload (`backend/app/upload/services.py:150-151` and
  `:232-233`). `frontend/src/store/ApplicationsContext.jsx`'s `applications` array is
  fetched once and only refreshed via its own `reload()`; document uploads go
  through `frontend/src/hooks/useDocuments.js`, whose `reload`/`upsertDocument` only
  touch `documentsByApplication`, never the `applications` list. So
  `ApplicationRow.jsx:27` (`application.name ?? <span>—</span>`) keeps showing the
  stale null name until the applications store is independently reloaded.

- **"Resume Application #8267" shows even while processing / already resumed** —
  `frontend/src/pages/Applications/ApplicationsPage.jsx:73-78`'s chip is driven
  purely by `useLastOpenedApplication` (`frontend/src/hooks/
  useLastOpenedApplication.js`), a `localStorage` pointer with no relation to
  application status. `recordOpened` fires unconditionally on every visit to
  `ApplicationDetailsPage.jsx:46`, and the hook's `clear()` is never called anywhere
  in the codebase — there is no "resumable" filtering logic at all.

### Critical

(#1, "missing auth on 40+ endpoints," moved to FALSE above — see the correction
note at the top of this file. Numbering below is kept as originally reported for
cross-reference, so this section starts at #2.)

2. **Refresh endpoint always sets `remember=True`** —
   `backend/app/auth/routes.py:221`: `_set_refresh_cookie(response,
   token_pair.refresh_token, settings, remember=True)` — hardcoded, ignoring the
   original login's `remember` choice (contrast `login()` at line 153, which
   correctly passes `remember=payload.remember`). A session-only login becomes a
   persistent 30-day cookie on first refresh.

3. **`ENVIRONMENT` defaults to `"development"` with no deploy-time enforcement** —
   `backend/app/core/config.py:105`: `environment: Environment =
   Field(default="development")`. The `_validate_environment` guard (lines 142-151)
   only fires when `environment == "production"`; a deployer who never sets
   `ENVIRONMENT` silently stays on the dev `secret_key` default and insecure
   cookies, unchecked.

### High

4. **`useVerification.js` missing request-ID guard** —
   `frontend/src/hooks/useVerification.js:89-106` (`reload`) has no request-ID ref
   at all, unlike `frontend/src/hooks/useHumanReview.js`
   (`appsRequestIdRef`/`reviewRequestIdRef`, lines 34, 40, 51, 79, 95), which guards
   specifically against stale-response races. Fast navigation between verification
   pages can show the wrong application's data.

5. **Document statuses all display as "Uploaded"** —
   `frontend/src/data/statuses.js:64-72` (`DOCUMENT_STATUSES`): `UPLOADED`,
   `PENDING`, and `COMPLETED` all map to `label: 'Uploaded', variant: 'success'`.
   Users cannot distinguish document lifecycle states.

6. **Commit before audit log, both in `confidence` and `normalization`** —
   `backend/app/confidence/services.py:412` (`self._db.commit()`) precedes
   `self._audit.create(...)` at line 418. `backend/app/normalization/
   services.py:106` (`self._db.commit()`) precedes `self._audit.create(...)` at
   line 107. A failed audit write after either commit leaves the state change
   persisted with no audit trail.

7. **`SKIPPED` processing outcome retried as a failure** —
   `backend/app/bulk_queue/workers.py:242-243`: `if result.outcome is
   ProcessingOutcome.SKIPPED: raise RuntimeError(...)`, caught by the surrounding
   `except Exception` (line 253) and routed into `mark_failed_attempt` (line 261) —
   consuming a retry attempt exactly like a genuine failure.

### Medium

8. **`useProcessingOverview.js` loading flash** —
   `frontend/src/hooks/useProcessingOverview.js:34`: `setLoading(false)` is the
   first line inside `reload`, executed before the `await listApplications(...)` on
   line 37 — an empty state flashes before data arrives.

9. **`ReportIssues.jsx` null reference** —
   `frontend/src/components/report/ReportIssues/ReportIssues.jsx:61` uses `issues ??
   []` for `groupIssues`, but line 65 accesses `issues.length` directly (the raw
   prop, not the guarded value) — crashes if `issues` is undefined/null.

10. **Focus trap missing in modals** —
    `frontend/src/components/common/ConfirmDialog/ConfirmDialog.jsx:52-92` and
    `frontend/src/components/auth/SessionTimeoutModal/SessionTimeoutModal.jsx:61-101`
    both use `role="alertdialog"`/`aria-modal="true"` but neither manages focus — no
    auto-focus on open, no Tab-key containment.

11. **`useProcessingProgress.js` polls unconditionally every 2.5s** —
    `frontend/src/hooks/useProcessingProgress.js:68-77` sets
    `window.setInterval(reload, 2500)` gated only by the
    `autoRefreshProcessingStatus` preference, with no `hasWork`-style check.
    Contrast `useProcessingOverview.js:86-95`, which only polls when `hasWork` is
    true.

12. **No rate limiting on login** — `backend/app/auth/routes.py:105-155` has no
    throttling logic; a codebase-wide search for rate-limiting libraries/middleware
    (slowapi, `Limiter`, throttle) found nothing.

13. **Read-then-write race on `application.status`** —
    `backend/app/upload/services.py:259-260` and `backend/app/bulk_queue/
    services.py:45-46` / `72-73` all use the same unguarded pattern (`if
    application.status is ApplicationStatus.SUBMITTED: self._applications.
    update(...)`) with no row locking or atomic compare-and-swap. Impact is mild
    (concurrent writers would set the same target value), but it's genuinely
    non-atomic.

14. **`useValidationReport.js` `loadApplications` missing request-ID guard** —
    `frontend/src/hooks/useValidationReport.js:69-84` (`loadApplications`) has no
    request-ID ref, while the sibling `reload` (lines 90-148) does use
    `reportRequestIdRef` — an inconsistent guard within the same file.

15. **`ApplicationTable` `SortIcon` defined inside render** —
    `frontend/src/components/applications/ApplicationTable/
    ApplicationTable.jsx:35-44`: `SortIcon` is defined as a new function on every
    render of `ApplicationTable`, so React treats it as a new component type each
    time and remounts it instead of updating props.

16. **`_process_bulk_upload` returns the wrong `ProcessingMethod`** —
    `backend/app/document_processing/services.py:300-306` returns
    `processing_method=ProcessingMethod.PADDLE_OCR` with `raw_text=""` immediately
    after splitting and enqueueing the split documents (line 292) for later async
    processing — no OCR has actually run against this result yet.

17. **`useValidationTask.js` `resultsData.results` possibly undefined** —
    `frontend/src/hooks/useValidationTask.js:41`: `setResults(resultsData.results);`
    with no `?? []` fallback, unlike other hooks in the codebase that guard
    similarly-shaped responses.

### Low

18. **`findNavItem` doesn't resolve `/validation-tasks`** — the route is real
    (`frontend/src/routes/AppRoutes.jsx:57`, `OperatorDashboardPage`) but absent
    from `NAVIGATION`/`NAV_ITEMS`/`ADMIN_NAV_ITEMS`/`INTERNAL_ROUTES` in
    `frontend/src/data/navigation.js`; `findNavItem` (lines 100-117) falls through
    to `NAV_ITEMS[0]` (Dashboard).

19. **Dead `user?.initials` fallback** —
    `frontend/src/components/layout/Sidebar/SidebarProfile.jsx:13` and
    `frontend/src/components/layout/Navbar/Navbar.jsx:33` both reference
    `user?.initials`; no `initials` field exists anywhere on the backend user
    model/schema, so the expression is always undefined.

20. **`[].every()` vacuous truth on empty checklist** —
    `frontend/src/components/humanReview/ReviewDecision/ReviewDecision.jsx:61`:
    `checklist.every((item) => item.is_checked)` returns `true` when `checklist` is
    empty, so the APPROVE validation error at line 69 never fires for an empty
    checklist.

21. **Download URL not application-scoped** —
    `frontend/src/services/documents.js:127-130` builds
    `${baseURL}/documents/${documentId}/download`, matching the actual backend
    route `backend/app/upload/routes.py:384-385` — unlike every sibling endpoint
    (list/upload/replace/delete), which is nested under
    `/applications/{application_id}/documents/...`.

22. **Base `AuthenticationError.status_code` is 500, not 401** —
    `backend/app/auth/exceptions.py:17`: `status_code: int = 500` on the base
    class. All concrete subclasses correctly override it to 401/403, so this only
    bites if the base class is ever raised directly — but as described, it's
    accurate.

23. **`REJECTED` in `RULE_RESULT_STATUSES` has no backend enum match** —
    `frontend/src/data/statuses.js:86` includes a `REJECTED` entry, but
    `backend/app/database/models/enums.py:57-63` (`ValidationStatus`) only defines
    `PASS`, `FAIL`, `WARNING`, `PENDING_MANUAL_REVIEW`.

24. **`document.status.toLowerCase()` no null guard** —
    `frontend/src/components/processing/ProcessingProgress/
    ProcessingProgress.jsx:75`, no guard for a null/undefined `status`.

25. **`context[field.ocr_result_id]` no `.get()` fallback** —
    `backend/app/normalization/services.py:92`:
    `context[field.ocr_result_id][0]` is a raw dict-index lookup, raises `KeyError`
    if `ocr_result_id` isn't in `context`.

### Root cause: uploaded documents never get processed

**Single-document upload never auto-starts processing.**
`frontend/src/utils/preferences.js:16`: `autoStartProcessingAfterUpload: false`
(default). `frontend/src/pages/UploadDocuments/UploadDocumentsPage.jsx:108-115`
(`maybeAutoStartProcessing`) reads that preference and returns early when falsy,
before ever calling `startProcessing`. Backend confirms the asymmetry:
`backend/app/upload/routes.py:203-239` (single-document `upload_document`) never
touches the queue at all, while `upload_bulk` (`backend/app/upload/
services.py:180-274`) unconditionally enqueues via
`QueueJobRepository.enqueue_uploaded_documents` (lines 254-258) regardless of any
preference.
**Fixed by `91307f8`** — `autoStartProcessingAfterUpload` default flipped to `true`
in both `preferences.js` and `UploadDocumentsPage.jsx`. Verified this is a complete
fix, not partial: `startProcessing()` (now called unconditionally after a
successful upload) hits a real, already-working, separate backend endpoint
(`POST /applications/{id}/processing/start`, `backend/app/bulk_queue/routes.py:85`)
— the backend note above explains why the frontend default mattered, it doesn't
describe a missing backend capability.

## Found during real-sample validation of merged extractors (not from the original teammate report)

Two issues below were found 2026-08-16 empirically validating `AccountMaintenanceCertificateExtractor`
(`bb3ebfb`, merged via PR #6) against the 5 real cached AMC samples in
`Confidential Data/.ocr_cache/` — separate provenance from the 32-item teammate
report above, kept in its own section so this doesn't get folded into that tally.
Neither is fixed; both are flagged for a scope decision, same framing as the
`branch_code`/`branch_name` gap documented in `CONTEXT.md`. Not attributed as
anyone's mistake — the extractor was built and unit-tested before any real AMC
sample was available to validate against, same situation every Phase 1 extractor
this session has started from.

**Garbage (not missing) `account_number` value on a combined "Account No/IBAN" label format.** One real sample (Allied Bank, `GDA_Abbotabad__ACCOUNT_MAINTENANCE_CERTIFICATE_copy1.txt`) labels account number and IBAN as a single combined field. `AccountMaintenanceCertificateExtractor`'s `account_number` pattern (`document_analysis/extractors.py`) matches the "Account No" portion of the label, then its capture group (`[A-Za-z0-9\-/ ]+`, which includes `/`) grabs the leading `/IBAN` text before the line's colon — empirically confirmed by direct call: `extract_fields()` returns `account_number == "/IBAN"` for this file. This is not a silent miss: `validate_account_number()` correctly flags it `invalid` ("Account number length is not plausible" — 0 digits after stripping), and end-to-end `scoring_components()` confirms the application lands on `NEEDS_REVIEW` (score 0.55), same practical outcome as if the field were honestly missing. The problem is what a reviewer sees in the meantime: a wrong, garbage-looking value (`/IBAN`) rather than an honest blank. Not fixed — needs either a stricter capture class (excluding `/`) or a dedicated combined-field pattern for this label shape.

**All three critical fields (`account_holder`, `account_number`, `iban`) come back empty for one real sample, root cause confirmed by direct regex testing, not the originally-suspected cause.** `DG_Sports_KP_Onboarding_Documents__ACCOUNT_MAINTENANCE_CERTIFICATE_copy1.txt` (Bank of Khyber) extracts nothing at all. Root cause, confirmed against the actual production regexes (not inferred from a generic label/value layout heuristic, which gave a misleading first read): this bank's certificate lists three parallel account entries as a migration history (old system → current system → Islamic-banking variant), and each entry's label is immediately followed **on the same line** by a bracketed system-name qualifier before any colon/dash separator (structurally: `<label> (<system qualifier>)`, value on the following line). For `account_number`, the regex *does* match — but its capture group can't cross the bracket (not in its allowed character class) and captures only the whitespace between label and bracket, which trims to empty and is correctly dropped as "missing" by the extractor's own trim-and-drop logic. For `account_holder` and `iban`, there's no match at all: no `account_holder`-style label appears anywhere in this file (the holder is only named in narrative prose), and `iban`'s capture group requires a strict IBAN-shaped value immediately following the label, which the next-line-only real value can never satisfy. All three fields being critical, this document deterministically routes to `NEEDS_REVIEW` — not a probabilistic risk, a certainty for this file's exact shape. **Blast radius checked against the other 4 real samples**: this exact same-line-bracket-then-next-line-value pattern was not found in any of them — all 4 captured real, correctly-shaped values for the fields their labels covered. So this specific failure mode is not something already silently degrading a currently-passing extraction elsewhere; it's demonstrated in 1 of 5 real samples, not a broader pattern already in play. It remains a real forward risk, though: the triggering layout (a bracketed account-system/type qualifier appended directly to a field label) is a bank-specific formatting choice already proven to occur once in these 5 samples, so it's plausible on a 6th, 7th, etc. department's certificate, not merely hypothetical. Not fixed — needs either a capture class that tolerates trailing bracketed qualifiers, or falling back to a next-line value when the same-line capture is empty.

## Notes (informational, not bugs)

**`human_verification/routes.py` per-route auth is inconsistent, but not a security
gap.** Found while re-establishing ground truth for Critical #1 (above): only
`submit_human_review` (line 138-143) declares `current_user: _CURRENT_USER` in its
signature. `get_human_review` (103-106) and `get_human_review_history` (178-181)
have no per-route auth parameter at all. This does **not** mean those two GET
endpoints are reachable without a session — `app/api/__init__.py`'s
`protected_router` wraps `human_verification_router` the same as every other
module, so all three still require a valid session. It's a real, previously
undocumented inconsistency in this file's own style (two handlers don't need the
`current_user` object and so never declared it; `submit_human_review` does need
it, for `reviewer_name`), worth knowing about if this file is ever touched for an
unrelated reason — not something to fix on its own.

## Suggested fix order (not started)

The teammate's own suggested order, minus #1 (authentication on routes — already
fixed 2026-08-14, see the correction note at the top), is a reasonable starting
point, not yet acted on:

1. Refresh token `remember` flag (Critical #2)
2. Document statuses display (High #5)
3. `useVerification` race condition (High #4)
4. Transaction/audit ordering (High #6)

Picking this up is a scope decision for whoever owns it next — this file only
records what was found and verified.
