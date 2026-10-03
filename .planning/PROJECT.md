# fs-pipeline-dart (P1) — 마일스톤 1: 비XBRL 원문 파서

## What This Is

DART 사업보고서 원문(`document.xml`, XBRL이 없는 문서)을 읽어 XBRL 수집 결과와 같은 형식의 재무제표 데이터를 만드는 파서다. 금융업 2022 이전처럼 XBRL이 없는 연도를 채워, 이후 프로젝트가 5개년 이상의 재무 데이터를 쓸 수 있게 한다. 같은 파싱에서 주석 표와 본문 문단도 뽑아 두어 N2·N9·M1(주석 표)과 P7(본문 단어·뉘앙스)이 재사용한다. 형식을 모르는 범용 층(`docparse`)은 새 레포로 승격하는 것을 전제로 짓는다.

## Core Value

원문에서 뽑은 재무제표 값이 같은 공시의 XBRL 값과 표시 단위 ±1 안에서 일치하고, 맞지 않으면 조용히 넘어가지 않고 멈춘다.

## Requirements

### Validated

<!-- 기존 코드가 이미 하는 일 (.planning/codebase/ARCHITECTURE.md) -->

- ✓ OpenDART `fnlttSinglAcntAll`로 연결재무제표(XBRL) 수집, 원본 JSON 보관 — existing (`dart.fetch_fs`, `collect.collect_one`)
- ✓ 공시목록 마지막 정정본 접수번호 대조 (D-004) — existing (`dart.last_rcept_no`, `dart.check_rcept`)
- ✓ 응답을 D-011 long 스키마 DataFrame으로 변환하고 parquet으로 저장 — existing (`dart.to_frame`, `collect.build_parquet`)
- ✓ 데이터 불변식 검사: 유일성 키, 접수번호, 자산총계 = 부채총계 + 자본총계(표시 단위 ±1) — existing (`validate.validate`, `validate.display_unit`)

### Active

- [ ] 공통 문서 모델: 섹션 경로 · 문단 · 표(원표 셀, 단위)를 원본 형식과 무관하게 표현한다
- [ ] DART 원문 리더: 최종 정정본 접수번호로 `document.xml`(zip)을 받아 공통 문서 모델로 바꾼다
- [ ] 범용 층 저장: 본문 문단(섹션 경로 포함)과 모든 원표(주석 표 포함)를 parquet으로 남긴다
- [ ] 재무제표 층 — 연결 재무상태표: 섹션 제목으로 표 1개를 특정(아니면 예외)하고, 단위를 환산해 D-011 스키마 + `source=document`로 낸다
- [ ] 재무제표 층 — 손익(IS·CIS)
- [ ] XBRL 쪽에도 `source=xbrl` 칸을 넣고(`dart.to_frame` 한 줄) 기존 parquet을 원본 JSON에서 다시 만든다
- [ ] 계정 매핑 사전: 같은 공시의 원문 행 금액과 XBRL 행 금액을 짝지어(표시 단위 ±1) 계정명 → `account_id` 사전을 자동으로 만들고, 짝이 없으면 수작업 사전으로 보완한다(작업자 승인). 회사별 사전, 조건을 만족하면 업종 공통 사전으로 올린다
- [ ] XBRL 대조 검증: v0 5사 × 2023~2025(공시 15개)에서 파서 결과가 XBRL과 전액 일치(L2). 항등식은 매 실행 L0, `dart-fss`는 보조 대조
- [ ] (조건부) KB금융 2015~2022 적용: 위 일치를 통과한 경우에만. 다음 해 보고서의 전기 열과 대조한다. 상한에 걸리면 이 항목만 뺀다

### Out of Scope

- 주석 의미 매핑(예: 특수관계자 표 → 정해진 칸) — 이번은 원표 추출까지. 다음 마일스톤
- 본문 텍스트 분석(어조·단어 빈도) — P7이 한다. 여기서는 문단 저장까지
- HTML · PDF · 외국 공시 리더 — 공통 문서 모델만 대비한다. 리더는 DART XML 하나
- `dart-fss` 출력을 파서 입력으로 쓰기 — 오염 방지(D-013). 비교용 선택 의존성으로만 둔다
- 비슷한 계정명 자동 허용(퍼지 매칭) — 정규화 후 정확히 같을 때만 적용(D-014)
- 비금융 기업의 과거 연도 파싱 — 2015부터 XBRL이 있다
- 별도재무제표 · 분기 · 2015 이전 — P1 Won't(D-001, D-012)
- Stage 1 게이트(무작위 표본 20건 원문 대조) — 별도 세션이 대화 안 경로로 한다. 이 마일스톤 밖

## Context

- 이 레포는 포트폴리오 커리큘럼 P1(2026-10-04 ~ 10-31)이고, 이후 모든 프로젝트가 import하는 공유 데이터 레이어다. 현재 Stage 1. 원문 파서는 P1의 Should 항목을 별도 세션(Opus)에서 앞당겨 하는 병행 작업이다. 인계: `docs/handoff-document-parser.md`
- 판단 원본은 `DECISIONS.md`다. 이 마일스톤은 D-004(정정공시) · D-009(금융업 연도) · D-011(스키마) · D-012(확장 연도) · D-013(직접 구현) · D-014(설계)를 따른다
- 실측 (KB금융 `00688996`, 2026-10-03):
  - 재무 API는 금융업 2022에 보고서 종류 × CFS·OFS 8조합 모두 `013`
  - `document.xml`은 zip 안에 xml 1개, 9.7MB, 표 약 2,200개, 단위 표기 십여 가지(억원 · 십억원 · 백만원 · 원 · 조원 등)
  - 자산·부채·자본총계를 모두 가진 표 9개 중 연결 표는 1개. 값: 자산 701,170,848 / 부채 651,527,934 / 자본 49,642,914(백만원), 항등식 차이 0
  - 2022 공시 3판(원공시 + 정정 2회) 모두 총계가 같았다. 2023 보고서 전기 열은 1117호 소급재작성으로 약 12.5조원 차이
  - 본문 표에는 `account_id`가 없다 → 계정 매핑이 필요하고 D-005(표준화 사전)의 씨앗이 된다
  - `dart-fss` 0.4.17은 재무상태표는 같은 값을 냈고 손익계산서는 `None`(원인 미조사), 의존 패키지 39개
- 커리큘럼: "주석 표 파서를 N2·N9·M1이 재사용한다"(P1 rev.4 메모). 공시 원문 본문은 P7·P11·N10이 쓴다
- 코드 지도: `.planning/codebase/` (2026-10-04)

## Constraints

- **Timeline**: 2026-10-09(금) 상한 — 넘기면 D-009 Won't를 유지하고 Stage 1 게이트로 돌아간다(D-014)
- **Packaging**: 범용 층은 `src/docparse/`, DART 재무제표 층은 `src/fs_pipeline_dart/` — 새 레포 승격이 거의 확실하므로 `docparse`는 `fs_pipeline_dart`를 import하지 않고, 테스트를 따로 두며, 의존성을 따로 적는다. 승격 때 폴더째 옮기고 `import docparse`는 그대로
- **Existing code**: `dart.py` · `collect.py` · `validate.py`는 건드리지 않는다 — 유일한 예외는 `dart.to_frame`에 `source` 한 줄(D-014)
- **Fail loud**: 표를 못 찾거나, 후보가 1개로 좁혀지지 않거나, 항등식이 어긋나거나, 핵심 계정(자산·부채·자본총계, 당기순이익)이 비면 예외 — 조용한 NaN 금지
- **Schema**: 재무제표 층 출력은 `dart.to_frame`과 같은 컬럼·타입 + `source`. 로더는 XBRL과 같게 당기만 내고 전기 열은 재작성 확인용 내부 표로만 둔다
- **Accounting judgment**: 수작업 계정 매핑은 AI가 제안하고 작업자가 승인한다 — 계정 분류는 회계판단
- **Stack**: Python 3.12, uv, pandas, pyarrow, logging(print 금지), ruff, pytest. 비밀값은 `.env`의 `DART_API_KEY`
- **Platform**: 플러그인 클래스·SDK는 P8 전에 만들지 않는다. P1 진입 함수(`analyze()`)는 이 마일스톤 범위가 아니다

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 파서를 직접 구현, `dart-fss`는 독립 기준값 (D-013) | 파싱 결과가 외부 패키지에 오염되지 않게. `dart-fss`는 주석 표 미지원 | — Pending |
| 범용 표 추출 층과 재무제표 층을 나눈다 (D-014) | 다른 공시, DART 밖 문서, 외국 재무제표로 범위를 넓힐 수 있다 | — Pending |
| L2 기준값 = 같은 공시의 XBRL (2023~2025) (D-014) | 코드와 독립인 원천. 항등식은 L0, `dart-fss`는 보조 | — Pending |
| 계정 매핑 = 값 짝짓기 자동 + 수작업 보완 (D-014) | 원문 표에 `account_id`가 없다. 같은 금액 행이 둘 이상이면 자동으로 짝짓지 않는다 | — Pending |
| 주석은 원표 추출까지 (2026-10-04) | 상한 10-09. 의미 매핑은 다음 마일스톤 | — Pending |
| 본문 문단을 섹션 경로와 함께 저장 (2026-10-04) | P7이 단어·뉘앙스 분석에 쓴다. 같은 파싱이라 추가 비용 작음 | — Pending |
| 리더는 DART XML 하나, 문서 모델은 형식 중립 (2026-10-04) | HTML·PDF·외국 공시 리더를 나중에 붙여도 아래 층이 안 바뀐다 | — Pending |
| KB금융 2015~2022 조건부 적용 (2026-10-04) | 5개년 이상 데이터가 목적. D-012 확장 범위와 맞춘다. 2015~2018 형식 차이 위험은 조사에서 확인 | — Pending |
| 위치 = P1 레포 안 독립 패키지 `src/docparse/` (2026-10-04) | 커리큘럼상 P1 파서를 다른 프로젝트가 재사용. 새 레포 승격을 전제로 경계를 지킨다 | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-10-04 after initialization*
