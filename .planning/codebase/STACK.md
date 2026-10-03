---
last_mapped_commit: ec4b60daf7f1272a503a43c3ac61909d07b1e3cd
last_mapped_at: 2026-10-04
---
# Technology Stack

**Analysis Date:** 2026-10-04

## Languages

**Primary:**

- Python 3.12 - All source code and application logic

## Runtime

**Environment:**

- Python 3.12 (specified in `.python-version`)

**Package Manager:**

- uv (version constraint: `uv_build>=0.12.12,<0.13.0`)
- Lockfile: `uv.lock` (present, committed)

## Frameworks

**Core:**

- pandas 3.0.6+ - Data manipulation and analysis (financial statement processing)
- pyarrow 25.0.1+ - Parquet file format support (data storage/export)

**HTTP & API:**

- requests 2.34.2+ - HTTP client for OpenDART API calls

**Configuration:**

- python-dotenv 1.2.4+ - Environment variable loading from `.env`

**Testing:**

- pytest 9.1.1+ - Test framework
- ruff 0.16.10+ - Linter and code formatter

## Key Dependencies

**Critical:**

- pandas - Core data frame operations for financial statement parsing and merging. Used in all processing stages (collection, standardization, validation)
- requests - HTTP client for OpenDART API calls. Single point of external integration

**Standard Library:**

- logging - Structured logging throughout (all modules use `logging.getLogger(__name__)`)
- pathlib - File path handling
- json - JSON parsing from DART API responses
- re - Regular expressions (amount parsing)
- os - Environment variable access (legacy, now via python-dotenv)
- argparse - CLI argument parsing
- datetime - Timestamp handling and formatting

## Configuration

**Environment:**

- `.env` file (git-ignored, `.env.example` provided as template)
  - `DART_API_KEY` - Required. API key from OpenDART (https://opendart.fss.or.kr)
- `.python-version` - Specifies Python 3.12

**Build:**

- `pyproject.toml` - Project metadata, dependencies, tool configuration
  - ruff lint settings: E, F, I, C4, DTZ checks enabled; E501 (long lines) disabled for Korean comments
  - pytest configuration: testpaths = ["tests"]

## Project-Specific Configuration

**Data Directories:**

- `data/raw/` - Original JSON responses from DART API (git-ignored)
- `data/processed/` - Parquet output files (git-ignored)
- `outputs/` - Analysis outputs (git-ignored except `.png` figures)

**Testing Directories:**

- `tests/fixtures/` - Committed test input data
- `tests/golden/` - Committed golden standard results

**Cache & Artifacts:**

- `.headroom-cache/` - forge headroom compression cache (git-ignored)

## Platform Requirements

**Development:**

- Windows 11 Home (project tested on)
- Git (for version control)
- Virtual environment: `.venv/` (created by `uv sync`, git-ignored)

**Execution:**

- Command: `uv run python -m <module>`
- Example: `uv run python -m fs_pipeline_dart.collect --corps 5 --years 2023-2025`

**Data Access:**

- Network connectivity to OpenDART (https://opendart.fss.or.kr)
- Valid OpenDART API key

---

*Stack analysis: 2026-10-04*
