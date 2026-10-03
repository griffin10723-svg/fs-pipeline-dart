---
last_mapped_commit: ec4b60daf7f1272a503a43c3ac61909d07b1e3cd
last_mapped_at: 2026-10-04
---
<!-- refreshed: 2026-10-04 -->

# Architecture

**Analysis Date:** 2026-10-04

## System Overview

```text
┌─────────────────────────────────────────────────────────┐
│                    OpenDART API Client                   │
│              `src/fs_pipeline_dart/dart.py`              │
│    (fetch_fs, last_rcept_no, check_rcept, to_frame)     │
└────────────────────────┬────────────────────────────────┘
                         │ raw JSON
                         ▼
┌─────────────────────────────────────────────────────────┐
│              Data Collection & Storage                   │
│            `src/fs_pipeline_dart/collect.py`             │
│    (collect_one, build_parquet, argparse entry)         │
└────────┬────────────────────────────────────┬───────────┘
         │                                     │
         │ data/raw/*.json (원본 보관)         │
         │                                     ▼
         │                              data/processed/
         │                              fs_long.parquet
         │
         └──────────────────────────────────────┬──────────┐
                                                │          │
                                  ┌─────────────▼───┐  ┌──▼──────────┐
                                  │   Validation    │  │  Data Load  │
                                  │ `validate.py`   │  │  (loaders)  │
                                  │  (check, v...)  │  │   (future)  │
                                  └─────────────────┘  └─────────────┘
                                          │
                                          ▼
                            ┌──────────────────────────┐
                            │  Platform Contract       │
                            │ analyze(subject,context) │
                            │  → 5-key dict (kpis,     │
                            │    tables, figures,      │
                            │    assumptions, sources) │
                            └──────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| DART API Client | OpenDART 호출, 응답 상태 검사, JSON → DataFrame 변환 | `src/fs_pipeline_dart/dart.py` |
| Collection Pipeline | 원본 JSON 저장, parquet 병합, 전후 행 수 검사 | `src/fs_pipeline_dart/collect.py` |
| Data Invariant Validator | 수집 후 데이터 품질 검증 (중복, 식별식 균형, 접수번호 일치) | `src/fs_pipeline_dart/validate.py` |
| Test Suite | 단위 테스트 (API 호출 모의), 불변식 검증 테스트 | `tests/test_dart.py`, `tests/test_data_invariants.py` |

## Pattern Overview

**Overall:** Functional data pipeline with contract-based platform integration

**Key Characteristics:**

- **No classes or SDK objects** — Functions only, until Stage 3 (follows platform 규칙)
- **Fail-fast on error** — Never silently convert bad data to NaN
- **Metadata alongside data** — Collect logs, metadata files (`.meta.json`) with each raw JSON
- **Invariant-as-check** — Before parquet write, validate() enforces 5 data rules
- **Accounting judgment explicit** — Every decision tied to D-number; code comments mark each

## Layers

**API Boundary (dart.py):**

- Purpose: OpenDART 호출 및 응답 변환
- Location: `src/fs_pipeline_dart/dart.py` (117 lines)
- Contains: `fetch_fs()`, `last_rcept_no()`, `check_rcept()`, `to_frame()`, `to_amount()`
- Depends on: `requests`, `pandas`, `python-dotenv`
- Used by: `collect_one()` → 수집 단계
- Design: 
  - 한 함수 = 한 책임. 네트워크, 파싱, 변환 분리
  - API 키는 환경변수만 쓴다 (D-001과 무관하지만 보안 규칙)
  - 응답 `status` 필드와 HTTP 상태 둘 다 검사한다 (금융업 2022 이전 D-009는 013 코드로 표기)

**Collection & Persistence (collect.py):**

- Purpose: 기업×연도별 JSON 저장 및 parquet 병합
- Location: `src/fs_pipeline_dart/collect.py` (93 lines)
- Contains: `collect_one()`, `build_parquet()`, `main()`, CLI args
- Depends on: `dart`, `validate`, `pathlib`, `logging`
- Used by: CLI 진입점 `uv run python -m fs_pipeline_dart.collect`
- Design:
  - 원본 JSON은 파일마다 저장하고 `.meta.json`에 수집 시각·행 수·접수번호 기록 (D-004 추적용)
  - `build_parquet()`는 concat (병합이 아니라 연결)이므로 전후 행 수가 정확히 일치해야 함을 assert로 강제
  - 로깅: 단계별 행 수와 파일명 기록 (merge 오류 추적용)

**Data Validation (validate.py):**

- Purpose: 로더 경계의 데이터 불변식 강제
- Location: `src/fs_pipeline_dart/validate.py` (90 lines)
- Contains: `check()` (규칙 목록), `validate()` (합치기 전 호출)
- Depends on: `pandas`, `logging`
- Used by: `build_parquet()` (parquet 저장 전 호출), 테스트
- Design:
  - 5가지 불변식: 유일성 키 중복 검사 · 의미 키 중복 검사(SCE 제외) · 재무제표 종류(sj_div) 범위 · 접수번호 일치(기업×연도마다 정확히 1개) · 자산-부채-자본 식별식 (D-001 회계판단 강제)
  - `_identity_errors()`: BS 자산총계 = 부채총계 + 자본총계, 반올림 오차는 표시 단위(원·천원·백만원) 내에서만 허용
  - 위반 시 ERROR 로그 + 예외 (조용히 진행 금지)

## Data Flow

### Primary Request Path: v0 수집

1. CLI `python -m fs_pipeline_dart.collect --corps 5 --years 2023-2025`
   - 기업 5개(D-008) × 연도 3개(D-009) = 15번의 호출
   
2. `collect_one()` — 기업×연도마다
   - `fetch_fs(corp_code, year)` → OpenDART API (fnlttSinglAcntAll.json)
   - 응답 `status`가 013(금융업 2022 이전)이면 WARNING 기록 후 None 반환
   - 응답 `status`가 000이 아니면 RuntimeError 발생 (실패-빠름)
   - `last_rcept_no()`로 공시목록에서 해당 기업·연도의 최종 정정본 접수번호 조회
   - `check_rcept()`로 응답의 모든 행이 같은 접수번호를 가진지 확인 (D-004)
   - JSON 파일로 저장: `data/raw/{corp_code}_{year}.json`
   - 메타데이터 저장: `data/raw/{corp_code}_{year}.meta.json` (행 수, 접수번호, 수집 시각)

3. `build_parquet()` — 수집 완료 후
   - 각 JSON 파일마다 `to_frame()` 호출 → DataFrame 변환 (스키마: D-011)
   - `pd.concat()` (중복 키 제외, 단순 행 연결)
   - assert: 병합 후 행 수 = 각 DataFrame 행 수의 합 (join이 아니므로 중복 불가)
   - `validate()` 호출 — 불변식 검사, 위반 시 parquet 저장 전 멈춤
   - `to_parquet()` 저장: `data/processed/fs_long.parquet`
   - INFO 로깅: 파일명, 행 수

**Schema (D-011 기준):**

```
corp_code: str          # 고유번호
fiscal_year: int        # 사업연도
sj_div: str             # 재무제표 종류: BS, IS, CIS, CF, SCE
account_id: str         # XBRL 표준계정ID (또는 NO_ID = "-표준계정코드 미사용-")
ord: int                # 순번 (재무제표 내 행 번호)
account_nm: str         # 계정 이름 (참고용, 조인에 미사용 — D-003)
account_detail: str     # 세부 항목 (SCE 구성요소 열 구분용, D-011 유일성 키 일부)
amount: Int64           # 금액 (원 단위, NA 허용)
currency: str           # 통화 (KRW)
rcept_no: str           # 최종 정정본 접수번호 (D-004)
reprt_code: str         # 보고서 코드 (11011 = 사업보고서)
```

**Row Count Tracking:**

- collect.log에 각 단계마다 행 수 기록 (추적용)
- 예: 삼성전자 2024 "수집 삼성전자 2024 행=2689 rcept_no=20250311001085"
- build_parquet()는 병합 후 행 수 = 입력 행 수의 합을 assert로 강제

### State Management

- **No in-memory state** — 각 기업×연도는 독립적으로 수집, 전후 행 수만 로깅
- **File-based checkpointing** — `data/raw/*.json` 존재하면 중복 수집 생략 (--force로 강제 재수집)
- **Parquet is authoritative** — 수집 재실행 후 build_parquet() 다시 호출하면 fs_long.parquet 덮어씀

## Key Abstractions

**금액 변환 (`to_amount`):**

- Purpose: 공시 금액 문자열(쉼표 포함) → 원 단위 정수
- Pattern: 빈 값 → pd.NA, 숫자 아님 → ValueError (조용히 NaN 금지)
- Example: `"514,531,948,000,000"` → `514531948000000`, `"-1,234"` → `-1234`, `""` → `pd.NA`
- 왜 이 방식: 금액 오류는 분석의 기초를 흔든다. 실패를 빨리 드러내야 한다(D-011 설계 원칙)

**유일성 키 (`KEY_COLS`):**

- Purpose: 중복 행 검사, 병합 대비 카디널리티 보증
- Columns: `corp_code`, `fiscal_year`, `sj_div`, `account_id`, `ord`, `account_detail`
- 왜 `account_detail` 포함: SCE(자본변동표)는 같은 `ord` 안에 구성요소가 여럿 있다. 이를 구분하려면 detail이 필요하다 (D-011)
- 검사: `df.duplicated(KEY_COLS).sum() > 0` → 유일성 키 중복 오류 (위반 시 InvariantError)

**의미 키 (`SEMANTIC_KEY`):**

- Purpose: 다른 계정을 같은 것으로 잘못 조인하는 오류 검사
- Columns: `corp_code`, `fiscal_year`, `sj_div`, `account_id` (detail 제외)
- 규칙: 표준 ID가 있는 행(`account_id` != NO_ID) 중 SCE 제외한 행은 의미 키가 유일해야 조인 가능 (D-003)
- 왜: IS와 CIS 모두에 같은 ID가 있을 수 있다. 값이 같으면 둘 다 유지하지만, 조인에는 한 행만 쓴다

**표시 단위 추정 (`display_unit`):**

- Purpose: BS 자산 금액들의 최대공약수로 표시 단위 유추
- Pattern: GCD(모든 금액) 계산, 단 최대값 1백만원(10^6)으로 상한
- 예: 가장 작은 금액이 5백만원 단위라면 GCD = 5,000,000
- 용도: 자산-부채-자본 식별식 검사 시 반올림 오차 허용 범위 결정 (D-001)

## Entry Points

**CLI Entry Point:**

- Location: `src/fs_pipeline_dart/collect.py` + `__main__` 블록
- Triggers: `uv run python -m fs_pipeline_dart.collect --corps 5 --years 2023-2025`
- Responsibilities: 
  - 인자 파싱 (기업 수, 연도 범위, --force)
  - 로깅 설정 (INFO 레벨, 파일 + 콘솔)
  - collect_one() 반복 호출
  - build_parquet() 한 번 호출
  - 실패 시 예외로 멈춤

**Test Entry Points:**

- `pytest tests/` — 모든 테스트 실행
  - `test_dart.py`: API 함수 단위 테스트 (네트워크 없음, fixture 사용)
  - `test_data_invariants.py`: validate() 불변식 테스트 (DataFrame 생성 후 검사)

**Platform Contract (미래):**

- Location: `src/fs_pipeline_dart/core/analyze.py` (Stage 2 예정)
- Signature: `analyze(subject: dict, context: dict | None = None, **params) -> dict`
- Inputs: `{"kind": "company", "corp_code": "00126380", "fiscal_year": 2024}`
- Outputs: `{"kpis": {...}, "tables": {...}, "figures": {...}, "assumptions": {...}, "sources": {...}}`
- Will replace: 로더 함수는 여기서 공급하고, parquet은 로더가 캐시

## Architectural Constraints

- **No classes before Stage 3** — Functions only. 이유: 플랫폼이 analyze() 함수만 기대하고, 클래스는 각 프로젝트의 내부 설계
- **Fail-fast on invariant violation** — validate()는 위반을 감지한 즉시 InvariantError 발생, 진행하지 않음
- **Single entry to parquet** — build_parquet()만 parquet 저장. 수집 재실행은 원본 JSON 재수집 → build_parquet() 재호출
- **No async/concurrency** — 단계별 순차 실행. Stage 2 이후 병렬화 검토
- **Python 3.12, uv로 의존성 관리** — pyproject.toml이 source of truth

## Anti-Patterns

### 자산-부채-자본 식별식을 무시

**What happens:** BS에서 자산총계, 부채총계, 자본총계를 읽었지만 자산 = 부채 + 자본을 검사하지 않고 넘어간다.

**Why it's wrong:** 공시 오류나 파싱 오류가 조용히 데이터에 남는다. 뒤 프로젝트에서 "왜 자산이 안 맞지?"라는 디버깅으로 시간이 낭비된다.

**Do this instead:** `validate()` 호출 전에는 parquet을 저장하지 말 것. `_identity_errors()`로 BS 모든 기업×연도 검사. 반올림 오차는 표시 단위 내에서만 허용할 것.

### merge 후 행 수를 검사하지 않음

**What happens:** `pd.merge(df1, df2, on=['corp_code', 'fiscal_year'])`를 했는데 반환 행 수가 예상과 다르다는 걸 나중에 발견한다.

**Why it's wrong:** 중복 키가 있으면 행이 불어난다(m:n이 n×m이 됨). 이걸 모르고 진행하면 나중에 분석 결과가 왜곡된다.

**Do this instead:** 모든 merge에 `validate="one_to_one"` 또는 `validate="many_to_one"` 인자를 반드시 넘길 것. 키 관계가 pandas 기대와 다르면 바로 에러가 나온다. concat은 validate가 없으니 전후 행 수를 assert로 확인할 것.

### 접수번호 검사 생략

**What happens:** DART API 응답의 `rcept_no` 필드를 읽지 않고, 공시목록의 최신 정정본이 실제로 응답에 들어왔는지 확인하지 않는다.

**Why it's wrong:** 정정공시가 있으면 같은 기업×연도에 여러 값이 섞일 수 있다. API가 항상 최신을 준다고 가정하면 안 된다(특히 1년 뒤 정정이 나오는 경우 — D-004).

**Do this instead:** `check_rcept()`로 응답 전 행이 같은 접수번호를 가진지 확인할 것. 그 접수번호를 sources에 기록할 것.

## Error Handling

**Strategy:** Fail-fast + explicit logging

**Patterns:**

- API 호출: `r.raise_for_status()` (HTTP 에러는 예외로), 응답 JSON의 `status` 필드 확인 (DART 자체 에러)
- 데이터 변환: 금액 → 숫자 변환 실패 → ValueError 발생 (조용히 NaN 금지)
- 로더 경계: validate() 위반 → InvariantError + ERROR 로그 (parquet 저장 전 멈춤)
- 로깅: 모든 수집 + 병합 단계마다 행 수 기록 (추적용)

## Cross-Cutting Concerns

**Logging:** `logging` 모듈 사용, 단계별 행 수와 파일명 기록

**Input Validation:** 경계(API 응답, 파일 읽기, CLI 인자)에서 검사

- 금액 문자열 → 숫자: 숫자 아니면 ValueError
- 접수번호 일치: 응답과 공시목록 대비
- 데이터 불변식: parquet 저장 전 validate() 강제

**Secrets:** `.env` + python-dotenv로 DART_API_KEY 관리, 코드에 절대 쓰지 않음

---

*Architecture analysis: 2026-10-04*
