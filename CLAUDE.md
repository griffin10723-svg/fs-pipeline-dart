# fs-pipeline-dart — P1

> DART 전자공시에서 상장사 재무제표를 자동 수집·표준화해, 이후 모든 프로젝트가 공유할 재무 데이터 레이어를 만든다.

이 저장소는 포트폴리오 커리큘럼(rev.5.2)의 첫 번째 본 프로젝트다 (2026-10-04 ~ 10-31, 4주).
작업자 배경과 학습 계약은 `~/.claude/CLAUDE.md`, 커리큘럼 공통 규칙은 `~/quant/CLAUDE.md`에 있고 둘 다 자동으로 로드된다.
이 프로젝트에서 작업자가 정하는 회계판단은 재무비율 산식과 계정과목 매핑이다 — 코드 전에 먼저 묻는다.

**세션을 시작하면 아래 "현재 단계"를 먼저 확인하고, 그 Stage의 게이트를 기준으로 작업을 제안한다.**

---

## Stage 0 — 스코프

**성공 기준:**
> 무작위 표본 20건(기업×연도)의 매출액·영업이익·자산총계가 DART 공시 원문과 100% 일치한다.

| | 내용 |
|---|---|
| **Must** | KOSPI200 × 2015~2025(11개년, D-012) 연결 재무제표(XBRL 전체 계정) 수집 · 계정과목 표준화 사전 · 재무비율 30종 산출 · 표본 대조 검증 노트북 · **다른 레포가 import할 로더 함수** · **`core/analyze.py`의 `analyze(subject, context=None, **params)` 진입 함수 + `SAMPLE`** |
| **Should** | 정정공시(재작성) 반영 · 결산월 변경 기업 처리 · parquet 캐싱 · **주석 표(특수관계자·충당부채·리스) 파싱 1건 시험** — N2·N9·M1이 재사용 (본격 구현은 Won't) |
| **Won't** | 코스닥 · 분기 데이터 · 별도재무제표 · 실시간 갱신 · 웹 UI · 금융업 2022 이전 연도(XBRL 없음, D-009) |

**표본 단위:** 1건 = 기업×연도. 무작위 추출 시드를 기록하고, 경계 사례(정정공시·결산월 변경) 1건 이상을 별도로 넣는다. 공통 규칙은 `~/quant/docs/00-curriculum.md` §4.1.

**v0 범위:** KOSPI200이 아니라 **5개 기업 × 3개년**. 이게 끝까지 관통한 뒤에 200개로 늘린다.

**현재 단계:** Stage 1 데이터 확보·검증 (2026-10-03 착수, 하루 앞당김)  ← 세션 시작 시 여기를 먼저 확인할 것. 게이트 체크리스트는 `ROADMAP.md`

**병행 작업:** 비XBRL 원문 파서(D-013)는 별도 세션(Opus)에서 한다. 인계 `docs/handoff-document-parser.md`. Stage 1 게이트(표본 20건)는 그대로 남아 있다.

**레포 문서 5종:** `README.md`(소개) · `ROADMAP.md`(Stage 게이트 진행) · `ARCHITECTURE.md`(모듈·데이터 흐름) · `CHANGELOG.md`(Stage별 변경) · `DECISIONS.md`(판단 원본)

---

## 데이터

- 출처: 금융감독원 전자공시 OpenDART API
- 취득: 단일회사 주요계정이 아니라 **XBRL 전체 재무제표 API**를 쓴다. 주요계정만으로는 팩터를 못 만든다.
- 인증키: `.env` 의 `DART_API_KEY`. **절대 코드에 쓰지 않는다.**
- 알려진 함정
  - 연결(CFS)과 별도(OFS)가 같은 응답에 섞여 있다. 구분 필드를 반드시 확인한다.
  - 계정과목명이 회사마다 다르다. 표준화 사전 없이 병합하면 조용히 틀린다.
  - 결산월 변경 기업은 한 해에 사업연도가 둘이거나 없을 수 있다.
  - 정정공시가 있으면 같은 기업·연도에 값이 두 개다. 재무 API(`fnlttSinglAcntAll`)는 최종 정정본 1판만 준다. 정정이 1년 뒤에도 나온다(KB 2024). 응답 `rcept_no`를 공시목록 마지막 정정과 대조한다(D-004).
  - 금융업은 2022 사업연도 이전 XBRL이 없다(`013`·`014`). 금융지주는 영업이익 ID가 `ifrs-full_ProfitLossFromOperatingActivities`다(D-009·D-010).
  - 자본변동표(SCE)는 `account_id`가 한 표 안에서 겹친다. 연도 간 비교·키 조인에 쓰지 않는다.
  - Windows에서 `python`은 Store 별칭이라 실패한다(exit 49). `uv run python`을 쓴다.
  - `merge` 후 행 수가 변하면 대개 중복 키다. 합칠 때마다 행 수를 확인한다
  - 유일성 키(`ord`·`account_detail` 포함)와 조인용 의미 키(`ord` 제외)를 나눈다(D-011). 표준 ID가 없는 `-표준계정코드 미사용-` 행은 의미 키가 겹치므로 조인에서 뺀다
  - 재무 API는 2015 사업연도부터 `000`이다(D-012). 금융업 2022 이전은 API 전 조합이 `013`이지만 원문(`document.xml`)에는 값이 있다(D-013)
  - requests 에러 메시지에는 인증키가 든 URL이 그대로 찍힌다. DART 호출은 `dart._get`으로만 하고, `r.url`을 로그에 남기지 않는다
  - `load_dotenv()`는 스크립트 위치에서 위로 `.env`를 찾는다. 다른 폴더의 스크립트는 `find_dotenv(usecwd=True)`를 쓴다
  - forge 커밋 게이트는 테스트의 `skipif`를 변조로 본다. 그런 테스트는 `test:` 단독 커밋으로 올린다. 훅이 막으면 같은 명령 안의 편집도 실행되지 않으므로 편집과 커밋을 나눠 실행한다.
- 검증: 표본 20건을 DART 웹 사업보고서 원문에서 눈으로 대조. 기록은 `docs/validation.md`와 `notebooks/verify.ipynb`.

---

## 플랫폼 연결

P1은 `deal-platform`의 **공유 데이터 레이어**가 된다. 이후 레포들은 DART를 다시 긁지 않고 이 레포의 로더 함수를 import한다. 그래서 로더의 함수 이름과 반환 형식(기업코드·연도·표준계정)을 v0부터 안정적으로 유지한다. P8에서 DuckDB `core.*` 구역으로 옮겨진다 — 로더는 DuckDB에 있으면 읽고, 없으면 DART에서 받아 저장하는 한 함수로 만든다.

동시에 P1 자신도 화면 하나를 가진다(⓪ 기업 개요). 진입 함수의 모양은 v0부터 이렇게 둔다.

```python
SAMPLE = {"kind": "company", "corp_code": "00126380", "fiscal_year": 2024}

def analyze(subject: dict, context: dict | None = None, **params) -> dict:
    # 5칸: kpis(2~4개) · tables · figures · assumptions(필수) · sources(필수)
    ...
```

| 이름표 필드 | 값 |
|---|---|
| `id` · `code` | `fs` · P1 |
| `stage` · `subject` | `overview` · `company` |
| kpi 후보 | ROE · 부채비율 · 영업이익률 · 매출 성장률 중 2~4개 (Stage 0에서 확정) |
| assumptions | 연결/별도 선택 · 정정공시 정책 · 계정 표준화 규칙 버전 |
| sources | DART 접수번호 |

상세는 `~/quant/docs/04-platform-architecture.md`.

---

## 이 프로젝트에서 반드시 짚고 가는 개념

코드를 쓰기 전에 아래 두 가지는 개념부터 확인한다. 둘 다 **에러 없이 조용히 결과를 바꾸는** 종류다.

- **결측치와 인덱스 자동정렬** — NaN은 경고 없이 계산 결과를 바꾼다
- **merge 후 행 수 변화** — 중복 키·결산월 변경·상장폐지로 행이 늘거나 줄고, 여기서 오염되면 뒤 프로젝트로 그대로 전파된다

그 밖에 이 프로젝트가 부르는 개념: API 호출과 JSON, 예외 처리, pandas 인덱싱, groupby·pivot, 문자열 벡터화, 정규표현식, 모듈 분리, OpenDART 사용법, DuckDB 기초.

---

## 실행

```bash
uv sync
cp .env.example .env        # DART_API_KEY 채우기
uv run python -m fs_pipeline_dart.collect --corps 5 --years 2023-2025   # v0 (D-009)
uv run python -m fs_pipeline_dart.standardize   # Stage 2
uv run python -m fs_pipeline_dart.ratios        # Stage 2
```

---

## 회계·재무적 판단

`DECISIONS.md`에 번호(D-001…)를 붙여 기록하고, README 3번 섹션에는 요약 표와 링크만 둔다. 코드에서는 `# 회계판단: D-번호` 주석을 남긴다.
결정된 것: D-001 연결 기준, D-002 ROE 범위 일치 원칙, D-004 정정공시·전기 재작성, D-008 v0 기업, D-009 v0 연도, D-010 금융업 CIR. 미정: D-005 표준화 규칙·D-002 세부(Stage 2 전), D-006 리스 1116호 비교가능성, D-007 판관비 분류. D-003 계정 식별 방법은 작업자 확인이 필요하다.

**비회계사 지원자는 이 판단 자체를 못 한다. 이 섹션이 차별화 지점이다.**

---

## 금지

- 요청하지 않은 리팩토링
