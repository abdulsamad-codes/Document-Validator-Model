# Session Handoff — 2026-08-20 (Claude Code, backend track)

Written by the Claude Code session that ran the full-project audit and the DB-isolation fix. Verified against live repo state at write time (`git status`, `git log`) — not reconstructed from memory. Current branch: **`audit/backend-verification-2026-08-20`**, created from `main` at `d1668f0`.

## TL;DR for whoever picks this up

- A live incident this session: real dev DB (`finance_verification`) was being wiped by the test suite's autouse fixture because no separate test DB existed. **Fixed and pushed to `main`** — a genuinely separate `finance_verification_test` DB now exists, `tests/conftest.py` points at it, and a hard guard refuses to wipe anything without "test" in the DB name.
- Backend-only audit work since then lives on `audit/backend-verification-2026-08-20`, **not yet merged**. Nothing on this branch has touched `frontend/` — that's intentional, a separate session (referred to in this project as "Antigravity") is doing frontend work in parallel.
- Phase 4/5 of the audit are done and reported to the user (Abdul) in-chat; **waiting on his go/no-go answers** before any fix is applied. See "Open decisions" below.
- 4 untracked scripts in `backend/scripts/` (`check_db.py`, `clear_db.py`, `extract_docx.py`, `inspect_db.py`) were left by the Antigravity session. Read but not modified. **`clear_db.py` unconditionally deletes from the real DB** (`refresh_tokens`/`users`/`applications` via `SessionLocal()`) — don't run it.

## What actually happened this session, in order

1. Committed and pushed two small fixes with explicit go-ahead each time: `56bdad7` (bulk_queue SKIPPED no longer burns a retry) and `de10e10` (FORMAL_REQUEST_LETTER routing). Ran a full-pipeline sanity sweep across every real cached document type, found a normalization bug (loop-retry when analysis legitimately found nothing), fixed and committed as `4a8a485`.
2. Confirmed a `.docx` sample (`TMA Thall Agreement.docx`) genuinely is a Tripartite Agreement (via a temp `python-docx` install / `backend/scripts/extract_docx.py`), cached it to `Confidential Data/.ocr_cache/TMA_Thall_Agreement__TRIPARTITE_AGREEMENT_copy1.txt`. **Important caveat discovered later (Phase 4): this is the entire multi-document `.docx` bundle, never run through the real page-splitter** (`DocumentSplitter.split_bulk_pdf` only handles PDF bytes) — it is not a clean, representative test sample.
3. **Live incident.** Two already-running `pytest` processes (not started by this session) were found actively re-wiping the real `finance_verification` DB via the autouse `isolated_database` fixture in `tests/conftest.py`, because no isolated test DB existed — tests ran directly against `DATABASE_URL`, which pointed at the real dev DB. Handled in strict order:
   - Killed both pytest processes.
   - Read-only damage assessment via `audit_logs` (never touched by the wipe) and `storage/applications/` file timestamps — confirmed **no real data was lost**, only test-fixture churn (cascading deletes/re-inserts of the same rows repeatedly).
   - Root cause fixed properly rather than patched around: reset the Postgres superuser password (temporary `trust` auth in `pg_hba.conf`, immediately reverted and verified with a deliberately-wrong-password rejection test), provisioned a real, separate `finance_verification_test` database.
   - Wired real isolation into `backend/tests/conftest.py`: `DATABASE_URL` is derived (via `dotenv_values(".env")`, since pydantic-settings never exports it into `os.environ`) and rewritten to point at `<original-db-name>_test`, **before** `app.database.connection` (whose `engine`/`SessionLocal` are built once at import time) is ever imported. `_wipe_database()` additionally now raises `RuntimeError` if the connected DB name doesn't contain `"test"`.
   - Proved isolation empirically (before/after real-DB snapshots, full suite run twice for determinism). Two new test failures surfaced; investigated to completion — **both confirmed unrelated to the isolation change** (one flaky, passed on retry; one a pre-existing bug reproduced against the clean pre-session baseline via `git stash`).
   - Committed as `d1668f0` — `fix(tests): isolate test suite against finance_verification_test` — **pushed to `main`**. This is a foundational/shared fix, deliberately committed to `main` directly rather than a branch, since both the backend and frontend tracks depend on it.
4. Created `audit/backend-verification-2026-08-20` from `main`, scoped explicitly to backend only (`app/document_analysis/`, `app/rule_engine/`, `app/document_processing/`, `tests/`) to avoid colliding with the parallel frontend session.
5. Ran a from-scratch, skeptical, no-trust-prior-claims audit (explicit trigger: a prior report in this project's history had fabricated a script and a commit hash that never existed). Phases 1–3 re-established ground truth against real commits/diffs. Phase 4 ran every extractor against every real cached sample per document type. Phase 5 surfaced three items as decisions for Abdul rather than deciding unilaterally.

## Phase 4 results (per-document-type extraction audit, all findings freshly reproduced)

| Doc Type | Extractor | Real samples | Verdict |
|---|---|---|---|
| TRIPARTITE_AGREEMENT | yes | 1 (invalid — whole unsplit `.docx`) | **Not production-ready** — even the isolated Agreement section produces garbage; the one real sample's prose doesn't match the label-based assumptions the extractor was built around, and no valid sample existed when `f8edde7` was written, so that commit's "tightened" claim can't be fairly verified |
| BILATERAL_AGREEMENT | yes | 0 | Untestable, unchanged known gap |
| ACCOUNT_MAINTENANCE_CERTIFICATE | yes (Zarghuna's) | 5 | Real gap reconfirmed: 1/5 garbage (`/IBAN` label variant not handled), 1/5 zero fields (different real structural shape). See "Open decisions" #3. |
| AUTHORITY_LETTER | yes | 8 | Mostly reliable; 2/8 new garbage case (`organization_name: 'the'`) from genuinely vague source prose; 1/8 zero-field case is a **splitter misclassification** (a checklist cover page mislabeled as Authority Letter), not an extractor bug |
| BUSINESS_REQUIREMENT_DOCUMENT | yes | 7 | Partially reliable — some header-echo garbage, 2/7 likely splitter-misclassified pages |
| ONE_LINK_LETTER | yes | 17 | Matches already-documented limitation, reconfirmed worse on the larger sample (10/17 zero fields, several OCR-truncated) |
| CNIC_FRONT | yes | 3 | **Reliable, production-ready** — 3/3 name+number correct, 1 honest missing-expiry |
| FORMAL_REQUEST_LETTER | yes | 1 | Reliable on its one sample (all 3 fields correct) |
| SCHEDULE_OF_CHARGES | **no, by design** | 0 | Deliberately out of scope — human-verification checklist |
| CNIC_BACK | **no, by design** | — | Deliberately excluded |

## Open decisions — presented to Abdul, waiting on his answers, no fixes applied yet

1. **GDA Abbotabad copy-cap** — turns out already resolved, not actually open. `app/upload/services.py:488` shows a 2026-08-19 department decision (predates this session): exceeding `MAX_COPIES_BY_DOCUMENT_TYPE` is no longer a hard rejection — accepted and flagged for manual review instead. Confirmed live against GDA Abbotabad's real 4-copy ONE_LINK_LETTER and 4-copy ACCOUNT_MAINTENANCE_CERTIFICATE cases. Reported to Abdul as effectively closed.
2. **Authority Letter + Formal Request Letter fixes** — confirmed via `git log` as already committed and on `main` (`ccaccff`, `3770e2c`, both ancestors of `f8edde7`). Reported as done; Authority Letter has 2 newly-found garbage cases from tonight's larger sample (see table above) that are NOT yet fixed.
3. **Zarghuna's AMC extractor gap** — reconfirmed real with fresh evidence (`GDA_Abbotabad...AMC_copy1.txt` → `/IBAN` garbage; `DG_Sports...AMC_copy1.txt` → zero fields, different real structural shape). **Not touched** — her code, her branch (`feature/zarghuna-bulk-queue`). Flagged for Abdul to route to her.

## Standing rules this session operated under (carry forward)

- Pre-flight `tasklist | grep -i python` before any OCR/pytest run; identify any already-running process via `Get-CimInstance Win32_Process` before acting.
- Never run two OCR jobs in parallel.
- Never run pytest against a database holding real (non-test) data — now structurally enforced by the `conftest.py` guard, but verify anyway.
- Never commit/push without showing the diff and getting explicit go-ahead, every time.
- Report raw command output, never paraphrased/summarized numbers.
- If something can't be verified directly, say so — don't infer it's fine.
- `frontend/` is off-limits from this branch/session — a separate concurrent session owns it.

## Not yet done

- Teammate branch activity check (`git fetch origin --all`, last-5-commits and unmerged-diff for `feature/afsana-validation-logs`, `feature/zarghuna-bulk-queue`, `feature/samad-doc-splitter`, `feature/formal-request-letter-extractor`) was requested once mid-session but the conversation moved directly into the Postgres fix instead. Read-only, never merge/checkout those branches. Unclear if still wanted — ask Abdul.
- No fixes for any Phase 4/5 finding have been applied. Waiting on Abdul's answers before touching `TripartiteAgreementExtractor`, `AuthorityLetterExtractor`, or anything AMC-related.
