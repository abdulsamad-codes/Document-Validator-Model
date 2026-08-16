# Phase: Complete remaining frontend UI (Validation Report, Human Review, Settings)

Approved scope. Do not modify Dashboard, Application Details, or Upload Documents.
Keep the six-item sidebar exactly: Dashboard | Applications | Upload Documents | Validation Report | Human Review | Settings.

## 1. Validation Report — /reports (replace PlaceholderPage)

### Services (new)
- `frontend/src/services/reports.js`
  - `getValidationReport(applicationId)` → GET `/applications/{id}/validation-report` (422 = no results)
  - `getValidationReportHtmlUrl(applicationId)` → printable HTML URL (new-tab)
- `frontend/src/services/technicalValidation.js` → GET `/applications/{id}/technical-validation`
- `frontend/src/services/analysis.js` → GET `/applications/{id}/analysis-results`
- `frontend/src/services/normalization.js` → GET `/applications/{id}/normalized-fields`
- Reuse: `verification.js` (`getCompleteness`, `getValidationResults`), `applications.js` (`listApplications`)

### Hook `frontend/src/hooks/useValidationReport.js`
- App picker via `listApplications({ status })`, default status `PENDING_REVIEW`, "All" option.
- On selection: parallel fetch report/completeness/technical/rules/analysis/normalized, each section caught individually (report 422 → empty state, others still render).
- Derived: `groupedRules` (by category_label: passed/failed/warnings/pending + items), `issues` (non-PASS rules + analysis doc issues), recommendations, `hasAnyData`.

### Page `frontend/src/pages/ValidationReport/ValidationReportPage.jsx` + `.module.css`
- Header, app picker (select), status filter, Refresh, "Printable report" link.
- Loading skeleton; empty state ("No validation results yet"); per-section errors.
- Sections (components under `frontend/src/components/report/`):
  - `ReportSummaryCards` — overall status + headline cards
  - `ReportDocuments` — document-by-document status (processing/ocr/technical/analysis)
  - `ReportCompleteness` — completeness result
  - `ReportTechnicalValidation` — technical validation detail
  - `ReportFields` — extracted + normalized fields
  - `ReportRules` — business rules grouped: Passed / Failed / Warning / Pending
  - `ReportVisual` — signature/stamp evidence summary
  - `ReportIssues` — issues requiring attention + recommendations

## 2. Human Review — /human-review (final review workflow)

### Routing
- Move shipped task queue: `OperatorDashboardPage` → explicit route `/validation-tasks` (internal, not in sidebar). Do NOT delete it.
- `/human-review` → new `HumanReviewPage`.

### Service `frontend/src/services/humanReview.js`
- `getReviewScreen(applicationId)` → GET `/applications/{id}/human-review`
- `submitHumanReview(applicationId, payload)` → POST `/applications/{id}/human-review`
- `getReviewHistory(applicationId)` → GET `/applications/{id}/human-review/history`
- Do NOT use `/confidence/review`.

### Hook `frontend/src/hooks/useHumanReview.js`
- App picker (default `PENDING_REVIEW`), select → parallel GET screen + application + history.
- `submit(payload)` → POST then refetch screen/app/history from backend (UI from real response).
- `alreadyReviewed` = `previous_review` present OR application status in APPROVED/REJECTED/CORRECTED → read-only, no submission controls.

### Page `frontend/src/pages/HumanReview/HumanReviewPage.jsx` + `.module.css`
- reviewer_name defaults to `useAuth().user?.name`.
- Sections (components under `frontend/src/components/humanReview/`):
  - `ReviewSummary` — application info, overall status, recommendations
  - `ReviewDocuments` — documents + OCR/processing state (+ collapsible OCR preview)
  - `ReviewFields` — extracted + normalized + confidence + verification status; per-field "Correct" toggle (value + optional reason); corrections list; already-reviewed fields marked, not re-flagable
  - `ReviewDetections` — signature/stamp present/missing + confidence
  - `ReviewChecklist` — full 15-item checklist (required for APPROVE)
  - `ReviewDecision` — APPROVE / CORRECT / REJECT; comments; rejection reason (REJECT); submit; client-side validation
  - `ReviewHistory` — previous reviews/decisions (read-only banner when already reviewed)

### Decisions
- APPROVE → all checklist items checked (backend enforces).
- CORRECT → ≥1 correction (field_name + corrected_value + optional reason).
- REJECT → rejection_reason required.
- Comments supported.

## 3. Settings — /settings (extend existing page)

- Profile card: name, email, employee id, role from `useAuth().user` (from `GET /auth/me`).
- Account/session card: signed-in state + functional Sign out via `POST /auth/logout` (`useAuth().logout()`).
- Password/security + preferences: informational "not available from the application" (no backend endpoint exists).
- Keep existing Administration section (Feedback, Continuous Learning) + restricted styling unchanged.
- Loading state while `useAuth().loading`.

## 4. Shared updates
- `data/statuses.js`: add `getRuleResultStatus(value)` → PASS=Passed/success, FAIL=Failed/danger, WARNING=Warning/warning, PENDING_MANUAL_REVIEW=Pending/neutral, REJECTED=Rejected/danger, fallback humanized/neutral.
- `data/navigation.js`: relabel "Validation Reports" → "Validation Report" (exact six-item bar).
- `routes/AppRoutes.jsx`: explicit routes `/reports`, `/human-review`, `/validation-tasks`; exclude `reports` from `PLACEHOLDER_ITEMS`; `human-review` already excluded.

## 5. Verification
- `cd frontend && npm run build` must pass.
- grep remaining `PlaceholderPage` usage (should remain only for admin + internal unfinished routes).
- Grep routes/imports for breakage.
- Verify every API call against the FastAPI routes/schemas read from source:
  - reports GET /validation-report, /validation-report/html
  - completeness GET /completeness
  - technical-validation GET /technical-validation
  - rule-engine GET /validation-results
  - document-analysis GET /analysis-results
  - normalization GET /normalized-fields
  - human-verification GET/POST /human-review, GET /human-review/history
  - upload GET /applications (status filter)
  - auth GET /auth/me, POST /auth/logout
- No mock/fake production data. No new backend modules. Backend tests only if backend changed (none expected).

## Reports at the end
- files created/changed, routes implemented, APIs connected, build result, remaining PlaceholderPages, genuine backend limitations.
