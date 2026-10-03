---
last_mapped_commit: ec4b60daf7f1272a503a43c3ac61909d07b1e3cd
last_mapped_at: 2026-10-04
---
# Codebase Concerns

**Analysis Date:** 2026-10-04

## Tech Debt

**Missing core.analyze() contract implementation:**

- Issue: Platform integration requires `core/analyze.py` with `analyze(subject: dict, context=None, **params) -> dict` returning 5-column dict (kpis, tables, figures, assumptions, sources) plus `SAMPLE`. Not yet implemented.
- Files: Placeholder needed at `src/fs_pipeline_dart/core/analyze.py`
- Impact: Cannot integrate into deal-platform. Stage 2 blocker. Other repos cannot import as shared data layer.
- Fix approach: Implement after Stage 1 validation gate passes. Contract shape fixed in v0, signature must not change (D-011).

**Incomplete standardization pipeline:**

- Issue: Stage 2 requires standardized account mapping (D-005) and financial ratio definitions (D-002 세부), but neither is implemented. Current code preserves all accounts from DART API with no filtering or renaming.
- Files: `src/fs_pipeline_dart/collect.py` (line 102), decision D-005 and D-002 미정
- Impact: Cannot calculate financial ratios. Cannot compare accounts across companies (account names vary: "영업이익" vs "영업이익(손실)"). Data is stored raw but not usable for analysis.
- Fix approach: Before Stage 2, work with user to decide: (a) which accounts to keep, (b) how to map company-specific names to standard IDs, (c) how to handle `-표준계정코드 미사용-` rows from non-XBRL or company-extensions. Decision must go in DECISIONS.md as D-005.

**No loader function for downstream repos:**

- Issue: Architecture promises `src/fs_pipeline_dart/loader.py` with reusable function for P2-P7 to import standardized data without re-fetching DART. Not implemented.
- Files: `src/fs_pipeline_dart/loader.py` (missing)
- Impact: Every downstream repo will fetch DART independently, violating platform design (D-011) and creating API quota waste + validation failures.
- Fix approach: Implement in Stage 2 after standardization is done. Must be stable from v0 onward; signature change = platform contract breach.

## Known Bugs

**Account_detail key is fragile in financial statements:**

- Symptoms: Statement of Changes in Equity (SCE) has same `account_id` in multiple rows with different components (자본금, 이익잉여금, 기타). Without `account_detail` in KEY_COLS, rows merge silently, losing data.
- Files: `src/fs_pipeline_dart/dart.py` (line 27), `src/fs_pipeline_dart/validate.py` (line 14)
- Trigger: Any merge by (corp_code, fiscal_year, sj_div, account_id) on SCE rows
- Workaround: D-011 정정 explicitly adds `account_detail` to uniqueness key. But if downstream code merges on 4-column key without detail, it will fail silently. Validation only catches this if data goes through `validate()`.

**Account filtering not yet implemented:**

- Symptoms: `to_frame()` preserves all rows from DART response including headers ("소계" with blank amounts) and company-specific extension accounts with no standard ID.
- Files: `src/fs_pipeline_dart/dart.py` line 102 comment: "계정은 거르지 않는다 (D-003)"
- Trigger: When downstream code tries to use raw data for calculations expecting only joinable rows.
- Impact: Calculations will include rows with `amount=NA` or non-standard IDs, polluting results.
- Workaround: Filter to `account_id != "-표준계정코드 미사용-"` before joins. But this is now "common knowledge" scattered across decision docs, not enforced in code.

## Security Considerations

**API key in environment variable vulnerable to log leakage:**

- Risk: `_api_key()` loads from `.env` via `python-dotenv`. If exception occurs in `fetch_fs()` or `last_rcept_no()`, requests lib may log URL with key or error handler might print env.
- Files: `src/fs_pipeline_dart/dart.py` (lines 34-37, 42-49, 57-65)
- Current mitigation: `.gitignore` blocks `.env` and `.env.*` except `.env.example`. No key appears in test fixtures. ruff rule T20 blocks `print()` outside tests.
- Recommendations: (1) Add `.headroom-cache/` to gitignore (already done). (2) Use logging instead of requests builtin error messages. (3) In Stage 4, add GitHub Actions check to detect secrets before push (forge commit-gate partial coverage, but human review on first push).

**Timezone handling in last_rcept_no():**

- Risk: `pd.Timestamp.today()` uses system timezone. If run on server with different TZ, might capture incorrect notice list (e.g., end_de boundary off by hours).
- Files: `src/fs_pipeline_dart/dart.py` line 61
- Current mitigation: Query end is "today", so 24-hour window is safe margin. DART corrections often come same day or days later, not hours.
- Recommendation: Use UTC-aware timestamp. Change to `pd.Timestamp.now(tz='UTC').normalize()` to be explicit.

## Performance Bottlenecks

**Sequential API calls with fixed 30-second timeout:**

- Problem: `collect_one()` makes two blocking API calls per corp/year (fetch_fs + last_rcept_no), each with timeout=30. Scaling to KOSPI200×11 years = ~6,600 calls = ~5+ hours with no retries or parallelization.
- Files: `src/fs_pipeline_dart/collect.py` lines 21-47, `src/fs_pipeline_dart/dart.py` lines 40-51, 54-77
- Cause: Single-threaded requests, no connection pooling, no async, no batch endpoints.
- Improvement path: (Stage 4 if time permits) Add retry logic (exponential backoff) and optional threading pool. DART API has no documented rate limits but FSS infrastructure is government-grade, usually stable. Don't add complexity until measured to be slow in production.

**Full DataFrame concat + validation before write:**

- Problem: `build_parquet()` loads all JSON files, converts to frames, concatenates in memory, validates, then writes. For KOSPI200×11 years (~500K rows × 16 columns), fits in RAM but is inefficient for CI/CD and error recovery.
- Files: `src/fs_pipeline_dart/collect.py` lines 50-64
- Cause: Simplicity. Single concat allows `assert len(out) == sum(...)` to catch lost rows.
- Improvement path: If parquet grows >500MB, switch to append-only parquet writer with `validate()` per-file before append. For v0 (56KB), not urgent.

## Fragile Areas

**Rcept_no validation assumes public API order:**

- Files: `src/fs_pipeline_dart/dart.py` lines 54-77
- Why fragile: `list.json` returns notices in `max(rcept_no)` order (string comparison as timestamp). If DART ever changes sort or filters by date range differently, this breaks silently. Code assumes one and only one "사업보고서" for corp×year with pattern `({year}.12)` in name.
- Safe modification: (1) Log full response to verify assumption holds. (2) Add test with mock DART responses (fixture not yet in tests/fixtures/). (3) Add condition: if multiple matches, pick max; if none, raise.
- Test coverage: `test_dart.py` has basic mismatch cases but no test for list.json response structure or name parsing. LIVE test would fetch real DART and cross-check.

**Amount parsing is regex-match with no safe fallback:**

- Files: `src/fs_pipeline_dart/dart.py` lines 88-98
- Why fragile: `to_amount()` uses `_INT.fullmatch(s)` after strip/comma removal. Rejects on any non-digit (e.g., "1.5조"). But if DART API ever returns unexpected format (e.g., unicode minus sign instead of ASCII `-`), will raise `ValueError` and halt pipeline mid-collect. No graceful degradation or detailed error context.
- Safe modification: Catch `ValueError`, log full value + context (corp, account, year), mark row as error, continue. Or add pre-processing step to detect and log anomalies before attempting conversion.
- Test coverage: `test_dart.py` has unit tests for `to_amount()` but fixtures are hand-coded. No test against real DART responses with edge cases.

**Validation.md sample list still empty:**

- Files: `docs/validation.md` lines 10-19
- Why fragile: Stage 1 gate requires "무작위 표본 20건" with seed recorded. Currently empty. If seed is not recorded before sampling, v0 data cannot be reproduced; downstream projects cannot validate against same baseline.
- Safe modification: Before finalizing Stage 1, run random.seed() with fixed seed (e.g., 42), draw 20 samples, record seed and list in validation.md, cross-check against DART web UI by hand.

**No golden snapshot to detect regressions:**

- Files: Missing `tests/golden/` baseline. ROADMAP requires it in Stage 2.
- Why fragile: If parquet schema or values change (e.g., account mapping rules applied), no automated check catches it. Only manual validation.md diffs would surface issue, and only if operator reviews.

## Scaling Limits

**Current scope: v0 = 5 companies × 3 years (15 records, 4,038 rows)**

- Parquet file: 56 KB
- Target scope: KOSPI200 × 2015~2025 (11 years) ≈ 2,200 companies × years
- Expected volume: ~200-300 KB parquet (rough linear estimate) + raw JSON ~2 GB (ignoring, per .gitignore)
- Limit: No hard limit identified yet. Network (API calls) is only constraint.

**API quota unknown:**

- Risk: DART OpenDART has no published rate limit. FSS infrastructure is robust but if quota exists and v0 triggers it silently (e.g., 013 response), full Stage 4 expansion will fail.
- Mitigation: D-009 note that KB금융 2022 returns 013 (no XBRL). If KOSPI200 scale returns many 013s, it may indicate quota hit, not missing data.
- Recommendation: Add `--dry-run` mode in Stage 2 to preview all corps/years before fetching, count by status code.

**SCE uniqueness fragility scales with data:**

- v0 data: 15 records pass unique-key validation (D-011). But if a single company's SCE has >20 capital components, `ord` alone might not disambiguate before `account_detail` was added. Good that fix was identified early.

## Dependencies at Risk

**No retry logic for requests library:**

- Risk: Network hiccup (connection reset, timeout, temporary FSS maintenance) will fail entire `collect_one()` call and require restart. For Stage 4 full run (6,600+ calls), probability of at least one hiccup is non-trivial.
- Mitigation: Already in ROADMAP Stage 1 "parquet 캐싱" — skip re-download if .json exists. But no auto-retry.
- Migration plan: Stage 2 or 4: Add `requests.Session` with Retry strategy (exponential backoff, max 3 retries).

**python-dotenv assumes POSIX path lookup:**

- Risk: `find_dotenv(usecwd=True)` walks up from cwd looking for `.env`. Behavior is platform-dependent. On Windows with `.venv\` hard-linked or symlinked, might find wrong `.env` from parent directory.
- Mitigation: `.env` is correctly in .gitignore. Tests use pytest fixtures, not `.env`.
- Recommendation: Explicit path `find_dotenv(Path.cwd() / '.env')` instead of auto-search.

## Missing Critical Features

**No parquet caching or incremental collection:**

- What's missing: If collection fails on corp N/year Y, restarting downloads all 1..N-1 again. For 6,600 calls, wasted bandwidth.
- Blocks: Stage 2 "명령 한 줄 end-to-end 실행" requires fast re-runs for development.
- Workaround: `--force` flag exists but encourages skipping cache. Opposite of incremental.
- Priority: High (Stage 2).

**No versioning strategy for account standardization:**

- What's missing: When D-005 is decided, if rule changes (e.g., new account added, classification changed), old parquet is now incompatible. No version tag in parquet to detect it.
- Blocks: P2+ downstream repos importing loader must know which D-005 version they're using.
- Workaround: None currently. DECISIONS.md records decision date but not version number.
- Priority: High (Stage 2, before creating loader).

## Test Coverage Gaps

**Golden snapshot tests not yet created:**

- What's not tested: If `to_frame()` or `validate()` behavior changes, no automated check detects regression (only manual DECISIONS.md diffs).
- Files: `tests/golden/` (missing)
- Risk: Stage 2 requires golden baseline for reproducibility; v0 data must be immutable reference.
- Priority: High (Stage 2 blocker per ROADMAP).

**Live test for DART API integration is marked skip:**

- What's not tested: Real DART responses with edge cases (정정공시, 결산월 변경, 금융업 2023, KB금융 1117호 restatement). Only mock fixtures in `test_dart.py`.
- Files: `tests/test_dart.py` has no `@pytest.mark.live` test, no fixture for KB금융 정정 scenario
- Risk: D-004 정정공시 handling is critical; only validated in hand-checked `docs/validation.md` pre-launch 3 samples.
- Priority: Medium (Stage 1 20-sample validation is manual, so live test can wait for Stage 3).

**Refutation tests not yet created:**

- What's not tested: Reverse checks (e.g., if ratio = earnings/equity, can we recover earnings from ratio × equity?). Only forward validation.
- Files: `tests/test_refutations.py` (missing, Stage 3 requirement)
- Risk: Silent errors in ratio calculations until Stage 3.
- Priority: Medium (Stage 3 gate requirement).

## Architectural Concerns

**No layered separation between API and business logic:**

- Issue: `dart.py` mixes API calls (fetch_fs, last_rcept_no), response parsing (check_rcept), and data transformation (to_frame, to_amount). Makes testing real responses without mocks harder.
- Files: `src/fs_pipeline_dart/dart.py` (whole file)
- Impact: High-level: no issue. Low-level: unit tests are all mocked; integration tests with real DART would be clearer.
- Fix approach: If D-013 비XBRL 원문 파서 is added, factor out a `_fetch_raw()` method so both XBRL and document parsers can be tested identically.

**validate.py business logic is tightly coupled to DART schema:**

- Issue: `validate()` checks hardcoded DART-specific invariants (KEY_COLS, SJ_DIVS, ANNUAL). If loader abstracts schema, validate() can't be reused.
- Files: `src/fs_pipeline_dart/validate.py` lines 8-18, 52-78
- Impact: P2-P7 will need separate validators. Code duplication risk.
- Fix approach: Move DART-specific checks (reprt_code==ANNUAL) into dart.py. Leave generic DataFrame checks (key uniqueness, NaN in amounts) in validate.py for reuse.

---

*Concerns audit: 2026-10-04*
