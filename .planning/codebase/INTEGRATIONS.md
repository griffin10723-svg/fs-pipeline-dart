---
last_mapped_commit: ec4b60daf7f1272a503a43c3ac61909d07b1e3cd
last_mapped_at: 2026-10-04
---
# External Integrations

**Analysis Date:** 2026-10-04

## APIs & External Services

**OpenDART (Korean Financial Disclosure Service):**

- API Base: `https://opendart.fss.or.kr/api`
- Purpose: Fetch consolidated financial statements (XBRL) for KOSPI200 companies
- SDK/Client: `requests` library (raw HTTP calls)
- Auth: API key via `DART_API_KEY` environment variable

**Endpoints Used:**

| Endpoint | Purpose | Location | Params |
|----------|---------|----------|--------|
| `fnlttSinglAcntAll.json` | Fetch single company full financial statement | `src/fs_pipeline_dart/dart.py:fetch_fs()` | corp_code, bsns_year, reprt_code="11011", fs_div="CFS" |
| `list.json` | Fetch filing list for validation (get latest receipt number) | `src/fs_pipeline_dart/dart.py:last_rcept_no()` | corp_code, bgn_de, end_de, pblntf_ty="A" |

**Response Format:** JSON

- Financial data: List of account entries with amounts, account IDs, fiscal year
- Filing list: Publication metadata including receipt numbers and report names

**Error Handling:**

- HTTP: `raise_for_status()` (raises on 4xx/5xx)
- API Status Codes: Checks response `status` field; "000" = success, "013" = no data (D-009)
- Custom: `RceptMismatch` exception for receipt number validation (D-004)

## Data Storage

**File Storage (Local Filesystem):**

- Raw data: `data/raw/{corp_code}_{year}.json` - Original API responses (git-ignored)
- Metadata: `data/raw/{corp_code}_{year}.meta.json` - Collection timestamp and receipt number
- Processed: `data/processed/fs_long.parquet` - Standardized consolidated table (git-ignored)

**File Formats:**

- JSON - Input/intermediate (API responses, metadata)
- Parquet - Output (Apache Arrow format via pyarrow 25.0.1+)

**Caching:**

- No external cache. Original JSON files serve as cache; re-fetch skipped if file exists (unless `--force` flag)

**No Database:**

- Local filesystem only (Parquet files)
- Future plan: P8 will move to DuckDB `core.*` integration (per CLAUDE.md platform architecture)

## Authentication & Identity

**Auth Provider:** Custom (OpenDART API key)

- Implementation: Environment variable `DART_API_KEY`
- Loading: `python-dotenv` via `.env` file
- Scope: Read-only access to public financial disclosures
- No token refresh or session management (stateless HTTP requests)

## Configuration

**Required Environment Variable:**

```
DART_API_KEY=<key>  # From https://opendart.fss.or.kr → 인증키 신청/관리
```

**Secrets Location:**

- `.env` file (git-ignored, template: `.env.example`)
- Never committed to repository
- Loaded at runtime via `dotenv.load_dotenv()`

## Monitoring & Observability

**Error Tracking:** None (errors logged but not sent to external service)

**Logs:**

- Method: Python `logging` module
- Format: Structured (event name + key=value pairs)
- Levels:
  - `ERROR` - Result cannot be trusted (API failure, malformed data)
  - `WARNING` - Processed with anomalies (missing data, no XBRL for year)
  - `INFO` - Step completion with metrics (fetch done, merge before/after row counts)
  - `DEBUG` - Detailed values
- Files: Logged to stdout/stderr (configurable in main entry point)

**Run Tracking:**

- Each run generates a unique `run_id` (planned, not yet implemented)
- Metadata saved alongside raw data (file creation timestamp, receipt number)

## CI/CD & Deployment

**Hosting:** Not deployed (local CLI tool)

**CI Pipeline:** None configured (developers run tests locally)

**Build System:**

- `uv_build` backend specified in `pyproject.toml`
- Package name: `fs-pipeline-dart`
- Version: 0.1.0

**Execution Model:**

- CLI: `uv run python -m fs_pipeline_dart.collect [options]`
- No server/daemon
- Designed as reusable module for other projects (P2, P3, etc.)

## Webhooks & Callbacks

**Incoming:** None

**Outgoing:** None

## Data Flow

```
OpenDART API
    ↓ (requests library)
    ↓ (JSON response)
data/raw/*.json (original)
    ↓ (dart.to_frame())
    ↓ (pandas DataFrame)
data/processed/fs_long.parquet (standardized)
    ↓ (import in other projects)
    ↓ (downstream analysis: P2 factors, P3 DCF, etc.)
```

## Known Constraints

- **Rate Limiting:** Not documented; 30-second timeout per request
- **Data Coverage:** KOSPI200 only; KOSDAQ excluded (Won't scope). No intraday/real-time data
- **Data Freshness:** Depends on DART publication schedule (annual reports, amendments)
- **Historical Data:** 2015~2025 (11 years) for most companies; some financial institutions lack XBRL before 2022 (D-009)
- **Amendment Handling:** Receipt numbers checked against latest filing list to detect restatements (D-004)

---

*Integration audit: 2026-10-04*
