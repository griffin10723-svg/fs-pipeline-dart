# 로드맵 — fs-pipeline-dart (P1, 2026-10-04 ~ 10-31)

**현재 단계:** Stage 1 데이터 확보·검증 (2026-10-03 착수, 계획보다 하루 앞당김). Stage 0 게이트 충족 2026-10-02.

다섯 단계의 게이트를 모두 통과해야 다음 단계로 간다. 일정이 밀리면 다음 단계로 넘어가지 않고 스코프를 줄인다.

## Stage 0 스코프 확정 — 충족
- [x] Must / Should / Won't 표 (Won't: 코스닥 · 분기 · 별도재무제표 · 실시간 갱신 · 웹 UI) — `CLAUDE.md`
- [x] 표본 단위 정의 (1건 = 기업×연도) — `docs/stage0-scope.md`
- [x] README에 문제 정의·성공 기준을 채운 첫 커밋

## Stage 1 데이터 확보·검증
- [x] 레포 표준 구조 (`src/`, `docs/`, `tests/`) 갖추기 (2026-10-03)
- [x] 착수 전 원문 대조 기록(3개사 2024)을 `docs/validation.md`로 옮기기 (2026-10-03)
- [x] v0 5개 기업 확정 (D-008), 연도 2023~2025 (D-009)
- [x] 정정공시 정책 결정 (DECISIONS D-004)
- [x] 연결재무제표 수집·원본 보관, 가공 결과 parquet — v0 5사×3년, 15건·4,038행 (2026-10-03)
- [x] 무작위 표본 20건 원문 대조 전액 일치 — 22건(경계 2 포함) 66개 값 불일치 0, 시드 20261007 (2026-10-09)
- [x] 대조 기록 — `docs/validation.md` (2026-10-09)
- [x] DART 불변식 `validate(df)` + `tests/test_data_invariants.py` 통과 (2026-10-03, v0 15건 gap 0) — 검사 항목은 결정 기록대로(D-001·D-003·D-004), 자산총계 = 부채총계 + 자본총계는 표시 단위 ±1 (forge 2.0, 2026-10-03)
- [x] `.claude/settings.json`에 forge-quant 켜짐 확인(`claude plugin list --json`) (2026-10-09)

## Stage 2 핵심 구현
- [x] 계정과목 표준화 규칙 결정 (DECISIONS D-005) (2026-10-09)
- [x] ROE 등 비율 산식 세부 결정 (DECISIONS D-002) (2026-10-09)
- [ ] v0 (5개 기업 × 3개년) 수집 → 표준화 → 비율까지 관통
- [ ] 다른 레포가 import할 로더 함수
- [ ] `core/analyze.py` — `analyze()` 5칸 dict + `SAMPLE` (`tests/test_contract.py` 통과)
- [ ] 골든 스냅샷 `tests/golden/` + 비교 테스트, 로컬 태그 `p1-stage2`
- [ ] 명령 한 줄 end-to-end 실행
- [x] merge 전후 행 수 전건 로깅 — Stage 1 게이트 재판정에서 FAIL(C3)을 받아 앞당겨 처리 (2026-10-10): `sample.py` merge 3곳 `validate=`·행 수 로그, `mapping.py` concat 3곳 행 수 로그
- [ ] ID 없는 행(`-표준계정코드 미사용-`) 안전장치 (2026-10-07, 원문 파서에서 나옴)
  - [ ] 로더는 ID 없는 행을 기본으로 빼고 옵션으로만 낸다 (account_id merge 행 수 폭증 방지)
  - [ ] 기업×연도별 비율 입력 계정 커버리지 표 ("매핑 못 함"과 "원래 없음"을 가른다)
  - [ ] 입력 계정에 ID가 없으면 비율은 0이 아니라 NaN + 사유 (D-015 원칙 확장)

## Stage 3 검증과 반증
- [ ] 독립 기준값 대조 — 핵심 지표마다 L2 이상 1건(원문 공시·감사보고서·KRX)
- [ ] 반증 5건 기록 + `tests/test_refutations.py`로 굳힘
- [ ] `/forge-quant:stage-gate` (args `{stage: 3}`) 후보표 검토

## Stage 4 문서화·패키징
- [ ] README 7섹션, 그림 3종 (파이프라인 도식 · 핵심 결과 그래프 · 검증 대조표)
- [ ] 새 폴더에서 clone → 설치 → 실행 성공
- [ ] KOSPI200 × 2015~2025(11개년)로 확장 (v0 통과 후, D-012). 금융업은 2023~2025만 (D-009)
- [ ] CHANGELOG에 v1.0 정리
- [ ] 면접 답변 카드 3장 초안 + 아직 설명 못 하는 질문 목록 마감
- [ ] `/forge-quant:stage-gate` (args `{stage: 4}`) 통과 — 플랫폼 연결은 P8에서 하므로 이 레포에서는 NA

## Should (시간이 남으면)
- 비XBRL 원문 파서 (D-013) — 새 세션에서 설계부터, 인계 `docs/handoff-document-parser.md`. 2023~2025 XBRL 일치가 적용 조건
- 결산월 변경 기업 처리 · parquet 캐싱 · 주석 표(특수관계자·충당부채·리스) 파싱 1건 시험
