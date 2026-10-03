---
last_mapped_commit: ec4b60daf7f1272a503a43c3ac61909d07b1e3cd
last_mapped_at: 2026-10-04
---
# Coding Conventions

**Analysis Date:** 2026-10-04

## Naming Patterns

**Files:**

- Module names: lowercase with underscores (`collect.py`, `dart.py`, `validate.py`)
- Test files: `test_*.py` pattern
- Package name: kebab-case with underscore in imports (`fs_pipeline_dart` = `fs-pipeline-dart`)

**Functions:**

- Lowercase with underscores (`to_amount()`, `collect_one()`, `build_parquet()`, `last_rcept_no()`)
- Helper functions prefixed with underscore (`_api_key()`, `_years()`, `_row()`, `_bs()`, `_identity_errors()`)
- No abbreviations unless domain-specific (DART API, sj_div for 재무제표 구분, etc.)

**Variables:**

- Lowercase with underscores: `corp_code`, `bsns_year`, `rcept_no`, `thstrm_amount`
- Constants: ALL_CAPS: `CORPS`, `KEY_COLS`, `BASE`, `ANNUAL`, `RAW`, `OUT`
- Single letters acceptable only in short loops and math: `g` for GCD in `display_unit()`, `e` for error lists
- Abbreviated units acceptable when semantic: `M = 1_000_000` (million won), `g` for gcd

**Types:**

- Custom exceptions: PascalCase ending in `Error` or `Exception`
  - `RceptMismatch` (receipt number mismatch)
  - `InvariantError` (data invariant violation)

**Constants and Decision References:**

- Decision references as inline comments: `# 회계판단: D-001`
- Dictionary keys from DART API kept as-is: `corp_code`, `bsns_year`, `account_id`
- Standard ID constants: `ASSETS`, `LIABILITIES`, `EQUITY` (IFRS standard codes)
- Sentinel values: `NO_ID = "-표준계정코드 미사용-"` (no standard account code)

## Code Style

**Formatting:**

- Tool: ruff (configured in `pyproject.toml`)
- Line length: 100 chars (E501 ignored for Korean comments)
- Import organization: stdlib → dependencies → local
  ```python
  import argparse
  import json
  import logging
  from datetime import datetime
  from pathlib import Path

  import pandas as pd
  import requests
  from dotenv import find_dotenv, load_dotenv

  from fs_pipeline_dart import dart
  from fs_pipeline_dart.validate import validate
  ```

**Linting:**

- Tool: ruff (rules in `pyproject.toml`)
- Enabled rules: E (errors), F (pyflakes), I (isort), C4 (comprehensions), DTZ (datetime)
- E501 (line too long) ignored for Korean comments
- Expected compliance: commit-gate enforces ruff passes before commit

**Comment Style:**

- Why, not what: `# 정정은 1년 뒤에도 나온다(KB 2024)` not `# get receipt number`
- Decision references required: `# 회계판단: D-001` or `# D-004`
- Multiline explaining complex logic: Kept minimal, logic should be self-evident
- Type and scope given for non-obvious values: `K_COLS = [...]  # D-011 유일성 키` (uniqueness key for D-011)

## Import Organization

**Order:**

1. Standard library (`argparse`, `json`, `logging`, `os`, `re`, `datetime`, `pathlib`)
2. Third-party (`pandas`, `requests`, `dotenv`)
3. Local modules (relative to `src/fs_pipeline_dart/`)

**Path Aliases:**

- None currently in use. All imports use full relative paths from package root.
- Example: `from fs_pipeline_dart.dart import CORPS` not `from .dart import`

## Type Hints

**Required:**

- All public function parameters and return types
  ```python
  def fetch_fs(corp_code: str, year: int) -> dict:
  def collect_one(corp_code: str, year: int, force: bool = False) -> Path | None:
  def to_amount(s: str) -> int | float | pd.NA:
  ```

**Patterns:**

- Union types use `|` (Python 3.10+): `Path | None`
- Return types always specified even if `None`
- Pandas dtypes: `pd.DataFrame`, `pd.Series`
- Nullable integers: `dtype="Int64"` (nullable pandas int, not Python int)

## Docstrings

**Format:** One-liner describing purpose, not implementation

```python
def to_amount(s: str):
    """금액 문자열을 원 단위 정수로. 빈 값은 NA, 그 밖에 숫자가 아니면 예외 (D-011)."""

def collect_one(corp_code: str, year: int, force: bool = False) -> Path | None:
    """원본 JSON을 받아 둔다. 이미 있으면 건너뛴다. 데이터가 없으면 None."""
```

**Decision Reference Required:** Docstrings must cite decision if accounting logic involved

```python
def fetch_fs(corp_code: str, year: int) -> dict:
    """연결(CFS) 전체 재무제표. 회계판단: D-001."""
```

## Error Handling

**Pattern:** Raise exceptions, never fail silently

```python

# Bad (forbidden):

try:
    body = r.json()
except:
    pass  # Silent failure

# Good:

r.raise_for_status()  # Fails explicitly
if body["status"] != "000":
    raise RuntimeError(f"{corp_code} {year}: {body['status']} {body['message']}")
```

**Custom Exceptions for Domain Errors:**

- `RceptMismatch` - receipt number doesn't match expected (D-004 violation)
- `InvariantError` - data invariant violated (validate.check() failures)

**API Error Handling:**

- HTTP: `requests.raise_for_status()` for network errors
- DART response: Check `status` field; `"000"` = success, `"013"` = no data, `"014"` = file not found
- Parsing errors: Raise `ValueError` with context

**Assertion Usage:**

- Used to catch code-level bugs, not data issues
  ```python
  assert len(out) == sum(len(f) for f in frames)  # concat must preserve row count
  ```

## Logging

**Framework:** Python `logging` module (not `print`)

**Module Pattern:**

```python
log = logging.getLogger(__name__)
```

**Setup (in `main()`):**

```python
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("outputs/collect.log", encoding="utf-8")
    ],
)
```

**Log Levels:**

- `ERROR`: Result cannot be trusted; invariant violated
  ```python
  log.error("불변식 위반: %s", e)
  ```
- `WARNING`: Processed but unusual; data exists but with known issues
  ```python
  log.warning("데이터 없음(013) %s %s", dart.CORPS.get(corp_code), year)
  ```
- `INFO`: Step completion + row counts; events with context
  ```python
  log.info("fetch_done corp=%s rows=%d rcept_no=%s", corp, len(df), rcept_no)
  ```
- `DEBUG`: Not used in current code

**Pattern: Events + Values, Not Narrative**

```python

# Good:

log.info("수집 %s %s 행=%d rcept_no=%s", corp_name, year, rows, rcept_no)
log.info("있음, 건너뜀 %s", path.name)

# Bad (avoid):

log.info(f"Successfully collected {rows} rows for {corp_name} in {year}")
log.info(f"The file {path} already exists, so we're skipping this one")
```

**Data Flow Logging:**

- Before/after row counts on merge/concat:
  ```python
  assert len(out) == sum(len(f) for f in frames)  # implicit logging
  log.info("저장 %s 행=%d", OUT, len(out))
  ```

**Secrets:** Never log API keys, tokens, or `.env` values

- Load from `python-dotenv` in `_api_key()`, never print
- Requests made to API logged only with sanitized params

## Pandas Conventions

**Merge Validation (Required):**

- Every `pd.merge()` call must include validate parameter:
  ```python
  df.merge(other, on="key", validate="one_to_one")
  df.merge(other, on="corp_code", validate="many_to_one")
  ```
- Catches silent duplicates that double row counts

**Data Type Convention:**

- Nullable integers: `dtype="Int64"` (capital I)
- Amount fields: nullable int64 for financial data
- Strings: object type, not categorical
- Datetime: `pd.Timestamp` for DART API dates

**NA Handling:**

- Blanks become `pd.NA` not `0` or `np.nan`:
  ```python
  return pd.NA  # not None or 0
  ```

## Files and Paths

**Tool:** `pathlib.Path` (not `os.path`)

```python
from pathlib import Path
path = RAW / f"{corp_code}_{year}.json"
path.exists()
path.write_text(...)
```

**Directory Structure:**

- `src/fs_pipeline_dart/` - Package source
- `tests/` - Test files
- `data/raw/` - Downloaded JSON (created runtime)
- `data/processed/` - Processed parquet (created runtime)
- `outputs/` - Logs and figures
- `docs/` - Documentation and decision records

## Environment and Configuration

**Secrets:**

- `.env` file (not committed) with `DART_API_KEY`
- Loaded via `python-dotenv`: `load_dotenv(find_dotenv(usecwd=True))`
- Never hardcode keys in source
- `.env.example` shows format without values

**JSON Encoding:**

- Always UTF-8 with `ensure_ascii=False` for Korean text:
  ```python
  json.dumps(data, ensure_ascii=False)
  path.write_text(json_str, encoding="utf-8")
  ```

## Function Design

**Size:** Functions in this project typically 5-30 lines; longest is ~45 lines

- Small, focused functions for single responsibilities
- Example: `to_amount()` does one thing (parse amount string)

**Parameters:**

- Type hints required
- Defaults allowed for optional parameters (`force=False`, `context=None`)
- Avoid `**kwargs`; explicit parameters

**Return Values:**

- Always typed
- `None` acceptable if valid (e.g., `Path | None` when data doesn't exist)
- Multiple related values → dictionary or dataframe, not tuple

**Example Function:**

```python
def to_frame(rows: list[dict]) -> pd.DataFrame:
    """응답 list를 D-011 스키마의 DataFrame으로. 계정은 거르지 않는다 (D-003)."""
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "corp_code": df["corp_code"],
        # ...
    })
    return out
```

---

*Convention analysis: 2026-10-04*
