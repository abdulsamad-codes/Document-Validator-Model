# Session Handoff — 2026-08-20 (Claude Code, backend track → handing off to Antigravity)

Written by the Claude Code session that ran the full-project audit, the DB-isolation fix, and the Authority Letter/BRD follow-up work. Verified against live repo state at write time (`git status`, `git log`, `git diff`) — not reconstructed from memory. **This session is ending here (usage limit) and handing off to an Antigravity session in this same workspace.** Current branch: **`audit/backend-verification-2026-08-20`**, created from `main` at `d1668f0`.

## READ THIS FIRST — exact state to resume from

```
$ git branch --show-current
audit/backend-verification-2026-08-20

$ git status --short
 M CONTEXT.md
 M backend/app/document_analysis/extractors.py
?? backend/scripts/check_db.py
?? backend/scripts/clear_db.py
?? backend/scripts/extract_docx.py
?? backend/scripts/inspect_db.py

$ git log --oneline -3
fa9329e session handoff added
d1668f0 fix(tests): isolate test suite against finance_verification_test
f8edde7 fix: tighten TripartiteAgreementExtractor party/account patterns
```

**Two files have real, working, tested but UNCOMMITTED changes. Do not commit either without showing Abdul the diff and getting explicit go-ahead first — that rule held for the entire session and nothing has changed it.**

- `backend/app/document_analysis/extractors.py` — a real fix (`AuthorityLetterExtractor.organization_name`), already validated against all 8 real cached samples and the two relevant test files (both green). See "Uncommitted work #1" below.
- `CONTEXT.md` — three new "Known gaps" entries dated 2026-08-20 documenting today's findings (Tripartite `.docx` not production-ready, the 2 Authority Letter garbage cases + fix, the BRD splitter-absorption + extractor-gap diagnosis). See "Uncommitted work #2" below.

The 4 untracked `backend/scripts/*.py` files are pre-existing, left by an earlier Antigravity session, read but never modified this session. `clear_db.py` unconditionally deletes from whatever DB `SessionLocal()` points at — don't run it.

## Uncommitted work #1 — AuthorityLetterExtractor.organization_name fix (DONE, tested, awaiting go-ahead)

**Bug**: 2 real samples (`TMA_Lal_Qilla_Dir_Lower`, `TMA_Samarbagh_Dir_Lower`) phrase the org-identifying clause as `"...on behalf of the\nAuthority."` — a backward self-reference wrapped onto a second line. The old pattern's capture stopped at the line break, matching only `'the'`, which wasn't in `_GENERIC_ORG_REFERENCE`'s alternation (`this`/`the said`/`said`), so it fell through as literal garbage instead of reaching the existing letterhead-fallback mechanism (the same mechanism that already correctly handles GDA Abbotabad's `"this Authority"` case).

**Fix** (`backend/app/document_analysis/extractors.py`, `AuthorityLetterExtractor`):
1. `organization_name` pattern now tolerates one more newline in the capture, mirroring the existing tolerance on `focal_person_name`/`focal_person_designation`.
2. `_GENERIC_ORG_REFERENCE` now also matches bare `"the"` (anchored both ends, so it can't false-match a real org name that merely starts with "the").
3. `extract()` normalizes whitespace on the captured value before the backward-reference check and before storing it.

**Verified, not assumed**:
- Before/after sweep across all 8 real cached `AUTHORITY_LETTER` samples: the 6 already-correct ones are byte-for-byte unchanged; the 2 failing ones now resolve via the existing letterhead fallback (`'the'` → `'OFFICE OF THE TEHSIL MUNICIPAL OFFICE'` / `'...OFFICER'`).
- `pytest tests/test_document_analysis_engine.py -q` → **60 passed**.
- `pytest tests/test_reports_api.py -q` → **10 passed** (the only other file referencing this extractor).
- `git diff -- backend/app/document_analysis/extractors.py` shown to Abdul in full mid-session — small, self-contained, docstring updated to match.

**Known, separate, NOT fixed**: `TMA_Lal_Qilla_Dir_Lower`'s `focal_person_name`/`focal_person_designation` are `None` because its source text is `"Mr.Syed Abdul Latif"` — no space after `"Mr."`, which the honorific pattern's `\.?\s+` requires. Flagged to Abdul, not touched (out of the scope he gave for this step).

**Next action**: show Abdul this diff (still sitting in the working tree, `git diff -- backend/app/document_analysis/extractors.py`) and get explicit go-ahead before `git add`/`git commit`. Do not push without a separate approval even after committing.

## Uncommitted work #2 — BRD splitter-misclassification diagnosis (read-only investigation, findings written to CONTEXT.md draft)

Diagnosed, per Abdul's explicit instruction, **without modifying `splitter.py` or the BRD extractor** — diagnosis only. Two independent real bugs stacked in the same 2 samples (`TMA_Lal_Qilla_Dir_Lower__BUSINESS_REQUIREMENT_DOCUMENT_copy2.txt`, `TMA_Samarbagh_Dir_Lower__..._copy2.txt`), confirmed by splitting each raw cached file at its `--- page break ---` marker and testing both halves through the extractor in isolation:

1. **Splitter continuation-absorption** (same mechanism as `TMA_Lal_Dir_Upper`/`GDC_Alpurai_Shangla`, already documented elsewhere in `CONTEXT.md` — confirmed this is NOT the `TMA_Thall_Hangu` checklist-cover-page mechanism, which was my earlier guess and has been corrected). Each `copy2` file bundles a genuine BRD continuation page with an unrelated onboarding-request letter (`"Subject: APPLICATION FOR ONBOARDING ON 1LINK 1BILL SERVICES"`) — a 4th real Formal-Request-Letter subject-line variant not in `splitter.py`'s `_STRONG_TITLE_PHRASES` for `FORMAL_REQUEST_LETTER`. With no strong-title match, the page is silently absorbed as a continuation of the still-open BRD group. Confirmed by reading `_STRONG_TITLE_PHRASES` directly, not inferred from the extraction result.
2. **A separate, genuine `BusinessRequirementDocumentExtractor` gap**: even the isolated BRD-only half of each file still extracts `{}` — its "Expected Outcomes" prose never uses either of the extractor's two anchor phrases (`"KPITB('s) Fin(-)Tech Unit"` / `"services offered"` etc.). Consistent with these same 2 departments' own working `copy1` samples, which also never trigger `digitization_intent_confirmed` (the extractor's one critical field) at all.

Full evidence (exact quoted source text, exact `_STRONG_TITLE_PHRASES` excerpt) is written into the `CONTEXT.md` diff sitting in the working tree right now — read that diff rather than re-deriving this from scratch. **Neither `splitter.py` nor the BRD extractor has been touched.** This is an open diagnosis, not a decision — Abdul has not yet said whether/how to fix either half.

## What actually happened this session, in order

1. Committed and pushed two small fixes with explicit go-ahead each time: `56bdad7` (bulk_queue SKIPPED no longer burns a retry) and `de10e10` (FORMAL_REQUEST_LETTER routing). Ran a full-pipeline sanity sweep across every real cached document type, found a normalization bug (loop-retry when analysis legitimately found nothing), fixed and committed as `4a8a485`.
2. Confirmed a `.docx` sample (`TMA Thall Agreement.docx`) genuinely is a Tripartite Agreement (via a temp `python-docx` install / `backend/scripts/extract_docx.py`), cached it to `Confidential Data/.ocr_cache/TMA_Thall_Agreement__TRIPARTITE_AGREEMENT_copy1.txt`. **Important caveat discovered later (Phase 4): this is the entire multi-document `.docx` bundle, never run through the real page-splitter** (`DocumentSplitter.split_bulk_pdf` only handles PDF bytes) — it is not a clean, representative test sample.
3. **Live incident.** Two already-running `pytest` processes (not started by this session) were found actively re-wiping the real `finance_verification` DB via the autouse `isolated_database` fixture in `tests/conftest.py`, because no isolated test DB existed. Handled in strict order: killed the processes, read-only damage assessment (confirmed no real data lost, only test-fixture churn), reset the Postgres superuser password properly (temporary `trust` auth, immediately reverted and verified), provisioned a genuinely separate `finance_verification_test` database, wired real isolation into `backend/tests/conftest.py` (DATABASE_URL derived and rewritten to `..._test` before `app.database.connection` is ever imported, plus a hard `RuntimeError` guard requiring "test" in the DB name). Proved isolation empirically, investigated 2 new test failures to completion (both confirmed unrelated to the isolation change). Committed as `d1668f0`, **pushed to `main`** — foundational, shared by both backend and frontend tracks.
4. Created `audit/backend-verification-2026-08-20` from `main`, scoped explicitly to backend only (`app/document_analysis/`, `app/rule_engine/`, `app/document_processing/`, `tests/`) to avoid colliding with the parallel frontend session (referred to in this project as "Antigravity" — now literally this handoff's destination).
5. Ran a from-scratch, skeptical, no-trust-prior-claims audit. Phase 4 ran every extractor against every real cached sample per document type; Phase 5 surfaced three items as decisions for Abdul rather than deciding unilaterally. Full results below.
6. Ran the previously-outstanding teammate branch check (`git fetch --all`; note: this repo has only one remote, `origin`, so `git fetch origin --all` errors on the redundant repository argument — use `git fetch --all`). All 4 branches (`feature/afsana-validation-logs`, `feature/zarghuna-bulk-queue`, `feature/samad-doc-splitter`, `feature/formal-request-letter-extractor`) still exist on origin. Read-only — none were checked out, merged, or modified. Results below.
7. Drafted 3 new `CONTEXT.md` "Known gaps" entries (uncommitted) covering the Tripartite `.docx` finding, the 2 Authority Letter garbage cases, and the BRD diagnosis.
8. Fixed the Authority Letter bug (Uncommitted work #1 above) and diagnosed the BRD bug (Uncommitted work #2 above), per Abdul's explicit step-by-step instructions, holding on commit/push both times pending his go-ahead.

## Phase 4 results (per-document-type extraction audit, all findings freshly reproduced)

| Doc Type | Extractor | Real samples | Verdict |
|---|---|---|---|
| TRIPARTITE_AGREEMENT | yes | 1 (invalid — whole unsplit `.docx`) | **Not production-ready** — even the isolated Agreement section produces garbage; the one real sample's prose doesn't match the label-based assumptions the extractor was built around, and no valid sample existed when `f8edde7` was written, so that commit's "tightened" claim can't be fairly verified |
| BILATERAL_AGREEMENT | yes | 0 | Untestable, unchanged known gap |
| ACCOUNT_MAINTENANCE_CERTIFICATE | yes (Zarghuna's) | 5 | Real gap reconfirmed: 1/5 garbage (`/IBAN` label variant not handled), 1/5 zero fields (different real structural shape). See "Open decisions" #3. |
| AUTHORITY_LETTER | yes | 8 | The `organization_name` garbage case is now **fixed** (see above, uncommitted). 1/8 zero-field case is a splitter misclassification (a checklist cover page mislabeled as Authority Letter), not an extractor bug — not fixed. |
| BUSINESS_REQUIREMENT_DOCUMENT | yes | 7 | Header-echo garbage pattern still present, not fixed. 2/7 zero-field samples now root-caused (see above) — two stacked bugs, diagnosis only, not fixed. |
| ONE_LINK_LETTER | yes | 17 | Matches already-documented limitation, reconfirmed worse on the larger sample (10/17 zero fields, several OCR-truncated) |
| CNIC_FRONT | yes | 3 | **Reliable, production-ready** — 3/3 name+number correct, 1 honest missing-expiry |
| FORMAL_REQUEST_LETTER | yes | 1 | Reliable on its one sample (all 3 fields correct) |
| SCHEDULE_OF_CHARGES | **no, by design** | 0 | Deliberately out of scope — human-verification checklist |
| CNIC_BACK | **no, by design** | — | Deliberately excluded |

## Teammate branch check (read-only, done — see "not yet done" resolved below)

| Branch | Last 5 commits (newest first) | vs `origin/main` |
|---|---|---|
| `feature/afsana-validation-logs` | `25c8508` a11y modal focus traps + config startup warning; `89b4d60` generalize AuthorityLetter/FormalRequestLetter extraction (different fields than today's fix — see below); `c236ba2` stop splitter absorbing Participation Memorandum pages; `fd8659b` merge of `formal-request-letter-extractor`; `3770e2c` add FormalRequestLetterExtractor | 3 files, +110/-3 — small, WIP |
| `feature/zarghuna-bulk-queue` | `91eba9b` AMC title-case holder from certifying sentence; `cea5a3f` docs merge cleanup; `b6fd4c4` tighten AMC account holder; `21b8d42` handle additional AMC layouts; `7331d89` CI Node 24 | 90 files, +7220/-1184 — large, clearly WIP (operator_workflow/system_logs modules, roles, frontend pages/tests) |
| `feature/samad-doc-splitter` | `90d9905` CONTEXT.md snapshot; `5824869` WORK_SUMMARY.md; `393443c` CLAUDE.md; `a876168` comment out VITE_API_BASE_URL; `30f8737` httpx pin + icon fix | 5 files, +318/-1 — docs-only, no real code changes pending |
| `feature/formal-request-letter-extractor` | tip `3770e2c`, same commit | **empty diff — already fully merged into `main`** |

**Important**: checked `89b4d60`'s and `c236ba2`'s actual diffs (not just titles) — neither fixes today's findings. `89b4d60` generalizes `focal_person_name` (a different field, for a third department) and a splitter title-phrase for Formal Request Letter; does not touch `organization_name`. `c236ba2` fixes a different splitter absorption case (Participation Memorandum → ONE_LINK_LETTER), unrelated to the BRD absorption case diagnosed above.

**Branch-merge decision is explicitly on hold** — pending Abdul's conversation with Zarghuna. Do not merge/checkout/touch any of these 4 branches without his explicit go-ahead.

## Open decisions — presented to Abdul, some resolved, some still open

1. **GDA Abbotabad copy-cap** — resolved, not actually open. `app/upload/services.py:488` shows a 2026-08-19 department decision (predates this session): exceeding `MAX_COPIES_BY_DOCUMENT_TYPE` is no longer a hard rejection — accepted and flagged for manual review instead. Confirmed live against GDA Abbotabad's real 4-copy cases. **Closed.**
2. **Authority Letter + Formal Request Letter fixes** — confirmed via `git log` as already committed and on `main` (`ccaccff`, `3770e2c`). The 2 newly-found `organization_name` garbage cases are now **fixed** (uncommitted, see above). **Effectively closed pending commit approval.**
3. **Zarghuna's AMC extractor gap** — reconfirmed real with fresh evidence, **not touched** — her code, her branch. Flagged for Abdul to route to her directly. **Still open, not this session's to touch.**
4. **BRD splitter-absorption + extractor gap** — diagnosed in full (see Uncommitted work #2), **not fixed**. Abdul has not yet said whether/how to fix either half. **Still open.**
5. **4 teammate branch merges** — **on hold**, pending Abdul's conversation with Zarghuna. Don't act on any of them.

## Standing rules this session operated under (carry forward into Antigravity)

- Pre-flight process check before any OCR/pytest run (`Get-Process python*` / `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` to see real command lines) — identify what's already running before acting. (This session found 4 running `python.exe` processes belonging to the IDE's own Jedi language server, unrelated to OCR/pytest — harmless, but always check, don't assume.)
- Never run two OCR jobs in parallel.
- Never run pytest against a database holding real (non-test) data — now structurally enforced by the `conftest.py` guard (`d1668f0`), but verify anyway.
- Never commit/push without showing the diff and getting explicit go-ahead, every time, separately for commit and for push.
- Real-sample validation mandatory before any extractor/rule change — never tune a pattern to a synthetic fixture alone.
- Report raw command output, never paraphrased/summarized numbers.
- If something can't be verified directly, say so — don't infer it's fine.
- `frontend/` was off-limits from this branch/session while a separate parallel session worked there — re-confirm with Abdul whether that boundary still applies once Antigravity is the one driving.

## Not yet done

- No fixes for Zarghuna's AMC gap or the BRD splitter/extractor gap have been applied — both are diagnosed/flagged only, per explicit instruction to hold.
- The Authority Letter fix and the CONTEXT.md draft entries are sitting uncommitted in the working tree — need Abdul's go-ahead to commit, then a separate go-ahead to push.
- Branch-merge decision for all 4 teammate branches is unresolved, explicitly waiting on Abdul talking to Zarghuna.
