---
last_mapped_commit: ec4b60daf7f1272a503a43c3ac61909d07b1e3cd
last_mapped_at: 2026-10-04
---
# Testing Patterns

**Analysis Date:** 2026-10-04

## Test Framework

**Runner:**

- pytest 9.1.1
- Config: `pyproject.toml` `[tool.pytest.ini_options]`
- Test discovery: `testpaths = ["tests"]`
- Assertion library: pytest built-in assertions

**Run Commands:**

```bash
uv run pytest              # Run all tests in tests/
uv run pytest -v          # Verbose output
uv run pytest tests/test_dart.py::test_to_amount_parses_won_integer_with_sign  # Single test
uv run pytest -k "blank"  # Filter by name
```

## Test File Organization

**Location:**

- Tests in `tests/` directory, separate from source in `src/`
- No nested test directories (flat structure)

**Naming:**

- Files: `test_*.py` pattern
- Current test modules:
  - `tests/test_dart.py` — unit tests for `dart.py` module (API, parsing, exceptions)
  - `tests/test_data_invariants.py` — validation tests for data integrity rules (invariants in `validate.py`)

**Pattern:**

- One test module per source module being tested
- Tests are isolated and can run without network or database

## Test Structure and Patterns

**Suite Organization:**

```python
"""dart.py 단위 테스트. 네트워크 없이 돈다."""

import pandas as pd
import pytest

from fs_pipeline_dart import dart
```

**Basic Test Function:**

```python
def test_to_amount_parses_won_integer_with_sign():
    assert dart.to_amount("514531948000000") == 514_531_948_000_000
    assert dart.to_amount("-1,234") == -1234  # Comment explains expectation
```

**Parametrized Tests:**

```python
@pytest.mark.parametrize("blank", ["", " ", "-"])
def test_to_amount_blank_is_na(blank):
    assert dart.to_amount(blank) is pd.NA
```

**Exception Testing:**

```python
def test_to_amount_rejects_non_numeric():
    with pytest.raises(ValueError):
        dart.to_amount("1.5조")

def test_check_rcept_matches_and_mismatches():
    # Happy path
    assert dart.check_rcept(rows, "20250311001085") == "20250311001085"
    # Error path
    with pytest.raises(dart.RceptMismatch):
        dart.check_rcept(rows, "20250401000001")
```

**Logging Assertions:**

```python
def test_validate_raises_and_logs_error(caplog):
    with pytest.raises(v.InvariantError), caplog.at_level("ERROR"):
        v.validate(_bs(100 * M, 60 * M, 30 * M))
    assert "불변식 위반" in caplog.text
```

**Conditional Tests (Skip Pattern):**

```python
@pytest.mark.skipif(
    not Path("data/processed/fs_long.parquet").exists(),
    reason="수집 결과 없음: collect를 먼저 실행",
)
def test_collected_v0_data_passes():
    assert v.check(pd.read_parquet("data/processed/fs_long.parquet")) == []
```

## Fixtures and Test Data

**Helper Functions (Not pytest Fixtures):**

- Named with leading underscore: `_row()`, `_bs()`
- Build test data with sensible defaults + overrides:
  ```python
  def _row(**kw):
      base = {
          "corp_code": "00126380", "bsns_year": "2024", "sj_div": "SCE",
          "account_id": "dart_EquityAtBeginningOfPeriod", "ord": "4",
          "account_nm": "기초자본", "account_detail": "자본금",
          "thstrm_amount": "100", "currency": "KRW",
          "rcept_no": "20250311001085", "reprt_code": "11011",
      }
      return base | kw  # Override with test-specific values
  ```

**Test Data Generators:**

- Build realistic data: `_bs(assets, liab, equity)` creates balance sheet with known relationship
- Use variables for magic numbers: `M = 1_000_000  # million won`
- Keep data minimal (3-row balance sheet, not full DART response)

**No Mocking Yet:**

- External API calls not mocked (network tests skipped in CI)
- Live DART tests marked separately (future: `@pytest.mark.live`)
- Unit tests work with parsed data, not network calls

## Testing Patterns

**Invariant Testing:**

- Test data integrity rules defined in `validate.py` check functions
- Each invariant tested as both pass and fail cases:
  ```python
  def test_clean_data_passes():
      assert v.check(_bs(100 * M, 60 * M, 40 * M)) == []

  def test_identity_gap_above_one_unit_fails():
      errs = v.check(_bs(100 * M, 60 * M, 38 * M))
      assert any("자산 - 부채 - 자본" in e for e in errs)
  ```

**Boundary Cases:**

- Empty/blank values: `["", " ", "-"]` become `pd.NA`
- Rounding tolerance: `±1 unit` in balance sheet identity
- Unicode/signs: Negative amounts `"-1,234"`, Korean text in errors

**Assertion Style:**

```python

# Simple equality

assert dart.to_amount("514531948000000") == 514_531_948_000_000

# Truthiness on collections

assert not df.duplicated(dart.KEY_COLS).any()

# Containment

assert any("자산 - 부채 - 자본" in e for e in errs)

# Type

assert df["amount"].dtype == "Int64"
```

**Error Message Expectations:**

- Test checks error message contains key words, not exact match:
  ```python
  assert any("유일성 키" in e for e in v.check(df))
  ```

## Verification and Standards

**Reference Data:**

- No external golden files yet (Stage 0 only)
- Planned for Stage 2: `tests/golden/` directory
- Planned for Stage 1 gate: 20-company reference validation in `docs/validation.md`

**Test Coverage:**

- Target: All public functions in parsing/validation modules
- Current coverage:
  - `dart.to_amount()` — complete (normal, blank, error)
  - `dart.check_rcept()` — complete (match, mismatch, multiple versions)
  - `dart.to_frame()` — partial (length, uniqueness, dtype, blank handling)
  - `validate.check()` — comprehensive (all invariants as pass + fail)
  - `validate.display_unit()` — complete (million, mixed, zero)

**Invariant-to-Test Mapping:**
| Invariant | Test | Decision |
|-----------|------|----------|
| Unique key on columns | `test_to_frame_keeps_every_row_and_key_is_unique_with_detail()` | D-011 |
| Blank → NA not zero | `test_to_frame_blank_amount_becomes_na_not_zero()` | D-011 |
| BS identity (assets = liabilities + equity) | `test_identity_rounding_within_one_unit_passes()` + `test_identity_gap_above_one_unit_fails()` | D-003 accounting assumption |
| One rcept_no per corp-year | `test_two_rcept_nos_for_one_company_year_fail()` | D-004 |
| No duplicate rows | `test_duplicate_key_fails()` | D-011 |
| Required rows present | `test_missing_total_row_fails()` | D-003 |

## Execution Requirements

**Dependencies (in `pyproject.toml` dev group):**

```toml
[dependency-groups]
dev = [
    "pytest>=9.1.1",
    "ruff>=0.16.10",
]
```

**Run from repo root:**

```bash
cd ~/quant/fs-pipeline-dart
uv sync               # Install (including test deps)
uv run pytest tests/  # Run all tests
```

**Expected Output:**

```
tests/test_dart.py::test_to_amount_parses_won_integer_with_sign PASSED
tests/test_dart.py::test_to_amount_blank_is_na[blank0] PASSED
tests/test_dart.py::test_to_amount_blank_is_na[blank1] PASSED
tests/test_dart.py::test_to_amount_blank_is_na[blank2] PASSED
...
====== 15 passed in 0.23s ======
```

## Test Data Types

**Pandas Conventions in Tests:**

- Build data with specific dtypes:
  ```python
  df = pd.DataFrame(rows).astype({"amount": "Int64"})
  ```
- Test nullable integers: `.isna()` not `.isnull()`
- Test missing values: `pd.NA` not `None`

**DART Response Simulation:**

- Dict list matching API schema:
  ```python
  rows = [
      {
          "corp_code": "00126380",
          "bsns_year": "2024",
          "account_id": "ifrs-full_Assets",
          "thstrm_amount": "514531948000000",  # Korean won as string
          "rcept_no": "20250311001085",
          ...
      }
  ]
  ```

**Constants for Financial Data:**

```python
M = 1_000_000  # Million won (표시 단위)

# Tests use multiples: 100 * M for 100 million won, etc.

```

## Test Isolation

**No Shared State:**

- Each test builds its own data with helper functions
- No setUp/tearDown (not needed; data created fresh per test)
- Tests are independent, order-independent

**No Network:**

- Network calls happen in `dart.py` module
- Tests of `dart.py` either stub responses or skip network tests
- Unit tests in `test_dart.py` test parsing, not API calls

**File System:**

- `test_collected_v0_data_passes()` skips if parquet doesn't exist
- Tests don't create output files (except via explicit data write)
- `data/` and `outputs/` gitignored, not checked during test

## Planning for Future Test Expansion

**Golden Snapshot Tests (Stage 2):**

- Save first complete v0 result to `tests/golden/v0_companies_2023-2025.parquet`
- Create test comparing current run to golden:
  ```python
  def test_current_equals_golden():
      current = build_parquet(v0_paths)
      golden = pd.read_parquet("tests/golden/v0_companies_2023-2025.parquet")
      pd.testing.assert_frame_equal(current, golden)
  ```

**Fixtures Directory (Stage 2):**

- `tests/fixtures/` for DART API response JSON examples
- `tests/fixtures/single_company/` for 삼성전자 2024 sample response
- `tests/fixtures/corner_cases/` for data edge cases (rounding, blank, etc.)

**Reference Validation (Stage 1 Gate):**

- `docs/validation.md` records 20 random sample reconciliation
- Not automated test; manual verification against DART web UI
- References: corp code, fiscal year, three metrics (매출액, 영업이익, 자산총계)

**Live Tests (Future):**

- `@pytest.mark.live` for tests that call real DART API
- Skipped in CI/CD
- Run manually for integration validation:
  ```python
  @pytest.mark.live
  def test_fetch_fs_returns_data_for_samsung_2024():
      result = dart.fetch_fs("00126380", 2024)
      assert result["status"] == "000"
      assert len(result["list"]) > 50
  ```

---

*Testing analysis: 2026-10-04*
