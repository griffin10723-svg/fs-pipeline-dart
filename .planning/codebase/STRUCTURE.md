---
last_mapped_commit: ec4b60daf7f1272a503a43c3ac61909d07b1e3cd
last_mapped_at: 2026-10-04
---
# Codebase Structure

**Analysis Date:** 2026-10-04

## Directory Layout

```
fs-pipeline-dart/
├── .claude/                     # 프로젝트 설정 (자동 로드)
├── .planning/                   # GSD 산출물 (codebase/ 내 이 파일들)
├── .gitignore                   # data/raw, outputs, .env 제외
├── .env.example                 # DART_API_KEY 템플릿
├── pyproject.toml               # 의존성 + pytest/ruff 설정
├── uv.lock                       # 잠금 파일
│
├── src/fs_pipeline_dart/        # 패키지 코드
│   ├── __init__.py              # 빈 파일 (패키지 표시)
│   ├── dart.py                  # OpenDART API 클라이언트 (117줄)
│   ├── collect.py               # 수집·병합·CLI (93줄)
│   └── validate.py              # 데이터 불변식 검사 (90줄)
│
├── tests/                       # 테스트
│   ├── test_dart.py             # dart.py 단위 테스트 (54줄)
│   └── test_data_invariants.py  # validate() 불변식 테스트 (89줄)
│
├── data/                        # 데이터 (git 추적 안 함)
│   ├── raw/                     # 원본 JSON (*.json + *.meta.json)
│   └── processed/               # 표준화 parquet (fs_long.parquet 예정)
│
├── docs/                        # 문서
│   ├── stage0-scope.md          # Stage 0 스코프 정의
│   ├── validation.md            # 검증 표본 및 결과
│   └── handoff-document-parser.md # 비XBRL 파서 인수인계
│
├── outputs/                     # 실행 로그 (git 추적 안 함)
│   └── collect.log              # collect.py 실행 로그
│
├── README.md                    # 레포 소개 (7섹션)
├── ROADMAP.md                   # Stage 게이트 진행표
├── ARCHITECTURE.md              # 구조 및 데이터 흐름
├── CHANGELOG.md                 # Stage별 변경 내역
└── DECISIONS.md                 # 회계·설계 판단 원본 (D-001 ~ D-014)
```

## Directory Purposes

**src/fs_pipeline_dart/:**

- Purpose: 모든 실행 코드. 패키지로 import 가능
- Contains: 함수만 (클래스 없음 — Stage 3 이후)
- Key files: `dart.py` (API), `collect.py` (pipeline), `validate.py` (rules)

**tests/:**

- Purpose: pytest 스위트
- Contains: 단위 테스트 (API 모의), 불변식 테스트 (DataFrame 검사)
- Run: `uv run pytest -q` (pyproject.toml에서 testpaths = ["tests"])
- Naming: `test_*.py`, 함수 `test_*`

**data/:**

- Purpose: v0 수집 데이터 (git 추적 안 함)
- raw/: 기업×연도마다 1개 JSON + 1개 메타 JSON. 예: `00126380_2024.json` + `00126380_2024.meta.json`
- processed/: `fs_long.parquet` (모든 기업×연도의 병합 parquet)

**docs/:**

- Purpose: Stage별 작업 문서
- validation.md: 표본 5+5+10 건과 원문 대조 결과 기록 (Stage 1 게이트)
- handoff-document-parser.md: 비XBRL 파서 구현 인수인계 (병행 작업, Opus)

**outputs/:**

- Purpose: 실행 로그. 각 세션마다 append
- collect.log: `logging.info`/`warning`/`error` 출력

## Key File Locations

**Entry Points:**

- `src/fs_pipeline_dart/collect.py`: `if __name__ == "__main__": main()` — CLI 진입 (`uv run python -m fs_pipeline_dart.collect`)
- `tests/test_dart.py`, `tests/test_data_invariants.py`: pytest 진입

**Core Logic:**

- `src/fs_pipeline_dart/dart.py`: DART API 호출, 응답 변환 (6개 함수)
- `src/fs_pipeline_dart/collect.py`: 수집 반복, JSON→parquet 병합 (3개 함수 + CLI)
- `src/fs_pipeline_dart/validate.py`: 불변식 검사 (2개 함수)

**Configuration:**

- `pyproject.toml`: Python 버전, 의존성, pytest/ruff 설정
- `.env`: DART_API_KEY (`.gitignore`에 제외)
- `.claude/settings.json`: 프로젝트 플러그인 설정 (자동 로드)

**Documentation:**

- `DECISIONS.md`: D-001~D-014 판단 원본 (코드 D-번호 주석으로 가리킴)
- `ROADMAP.md`: 5단계(Stage 0~4) 진행 체크리스트
- `ARCHITECTURE.md`: 계층·데이터 흐름·불변식

## Naming Conventions

**Files:**

- 모듈: `snake_case.py` — `dart.py`, `collect.py`, `validate.py`
- 테스트: `test_<모듈>.py` — `test_dart.py`, `test_data_invariants.py`
- 데이터: 기업×연도 JSON: `{corp_code}_{year}.json` — `00126380_2024.json`
- 메타: `{corp_code}_{year}.meta.json`
- 문서: `UPPERCASE.md` — `DECISIONS.md`, `README.md`, `ARCHITECTURE.md`

**Directories:**

- 패키지: `snake_case` — `fs_pipeline_dart`
- 데이터: 단계 `raw` / `processed`
- 문서: `docs/`

**Functions:**

- `snake_case` — `fetch_fs()`, `collect_one()`, `validate()`, `to_frame()`
- 비공개: `_로 시작 — `_api_key()`, `_years()`, `_identity_errors()`

**Variables:**

- 상수: `UPPERCASE` — `BASE`, `ANNUAL`, `NO_DATA`, `CORPS`, `KEY_COLS`, `ASSETS`, `LIABILITIES`, `EQUITY`
- 로컬: `snake_case` — `corp_code`, `frame`, `paths`, `out`

**Types:**

- Columns: `snake_case` 또는 XBRL ID — `corp_code`, `fiscal_year`, `amount`, `ifrs-full_Assets`
- Exceptions: `PascalCase` — `RceptMismatch`, `InvariantError`

## Where to Add New Code

**New Feature (Stage 2 표준화):**

- Primary code: `src/fs_pipeline_dart/standardize.py` (새 파일)
  - Contents: 계정 표준화 로직 (계정 매핑 사전, 식별 규칙 D-005)
  - Pattern: 함수들, `standardize(df_raw: pd.DataFrame) -> pd.DataFrame`
- Tests: `tests/test_standardize.py`
  - Test data: 기존 `data/raw/` 또는 fixture로 표본 DataFrame 생성
- CLI: `collect.py` 또는 새 진입점 `uv run python -m fs_pipeline_dart.standardize`

**New Module (Stage 3 재무비율):**

- Implementation: `src/fs_pipeline_dart/ratios.py`
  - Contents: 재무비율 30종 계산 함수 (ROE, 부채비율, 영업이익률 등)
  - Pattern: `calculate_ratios(df_standardized: pd.DataFrame) -> pd.DataFrame`
- Tests: `tests/test_ratios.py`
  - Fixture: 표준화된 parquet의 표본 (또는 직접 생성)
  - Benchmark values: 독립 기준값(DECISIONS.md D-002 세부 선택 후)
- CLI: `uv run python -m fs_pipeline_dart.ratios`

**Platform Entry (Stage 2 말 예정):**

- Location: `src/fs_pipeline_dart/core/analyze.py` (새 폴더 + 파일)
- Signature: `analyze(subject: dict, context: dict | None = None, **params) -> dict`
- Contents:
  ```python
  SAMPLE = {"kind": "company", "corp_code": "00126380", "fiscal_year": 2024}
  
  def analyze(subject, context=None, **params):
      # kpis, tables, figures, assumptions, sources 5칸 반환
  ```
- Tests: `tests/test_analyze.py` (platform contract 테스트)

**Utilities & Helpers:**

- Shared conversion: `src/fs_pipeline_dart/common.py` (또는 `_utils.py`)
  - Pattern: 함수만, 모듈 외부 import 가능
  - Example: 통화 변환, 표시 단위 관련 함수
- Data fixtures: `tests/conftest.py` (pytest fixture 중앙 정의)
  - Pattern: pytest `@pytest.fixture`, 테스트들이 `import conftest` 또는 직접 사용

## Special Directories

**data/raw/:**

- Purpose: 원본 API 응답 보관 (git 추적 안 함)
- Generated: `collect.py` 실행 시 생성
- Committed: 아니오 (`.gitignore`)
- 파일명: `{corp_code}_{year}.json` + `{corp_code}_{year}.meta.json`
- Metadata fields: `corp_code`, `year`, `rows`, `rcept_no`, `last_rcept_no_match`, `fetched_at`

**data/processed/:**

- Purpose: 표준화 데이터 저장 예정 (Stage 2)
- Generated: `collect.py` → `build_parquet()` (현재), 이후 표준화 코드
- Committed: 아니오 (`.gitignore`)
- File: `fs_long.parquet` (현재), 향후 `fs_standardized.parquet` 등

**outputs/:**

- Purpose: 실행 로그 및 결과물 임시 저장
- Generated: CLI 실행 시 append (collect.log)
- Committed: 아니오 (`.gitignore`)

**.planning/codebase/:**

- Purpose: GSD 산출물 (이 문서들)
- Generated: gsd-map-codebase 명령
- Committed: 예 (documentation, 자동 갱신)
- Files: `ARCHITECTURE.md`, `STRUCTURE.md` (이번 실행), 향후 `CONVENTIONS.md`, `TESTING.md` 등

## Import Paths

**Internal imports (같은 패키지):**

```python
from fs_pipeline_dart import dart
from fs_pipeline_dart.validate import validate
```

**External imports:**

```python
import pandas as pd
import requests
from dotenv import load_dotenv
```

**Test imports:**

```python
from fs_pipeline_dart import dart
from fs_pipeline_dart.validate import InvariantError, check
```

**No barrel files yet** — `__init__.py`는 빈 상태. Stage 2 이후 공개 API 정의 시 `__all__` 추가.

---

*Structure analysis: 2026-10-04*
