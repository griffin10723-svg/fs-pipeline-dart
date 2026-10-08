# 인계: 클라우드 세션 → 로컬 세션 (2026-10-07)

브랜치 `claude/inspiring-keller-gjtjbi`. 아직 main에 합치지 않았다.

## 로컬에서 할 일

### 1. Stage 1 원문 대조 (작업자)

`data/`와 `outputs/`는 커밋하지 않으므로 로컬에서 다시 만든다.

```bash
git fetch origin claude/inspiring-keller-gjtjbi && git checkout claude/inspiring-keller-gjtjbi
uv sync
uv run python -m fs_pipeline_dart.collect --corps 5 --years 2021-2025
uv run python -m fs_pipeline_dart.sample --seed 20261007 --boundary 00688996:2024 --boundary 00258801:2023
```

- 출력된 표가 `docs/validation.md` 표와 같은지 먼저 본다(시드 재현). 다르면 대조를 시작하지 않는다.
- `outputs/sample.csv`의 `source_amount`에 원문 값을 넣는다. 원문은 `validation.md` 표의 접수번호 링크(최종 정정본) → "III. 재무에 관한 사항 > 2. 연결재무제표".
  - 쉼표 없이 숫자만, `(1,234)`·`△`는 `-1234`.
  - `unit`: 표 머리 `(단위 : …)`. **카카오는 원 단위라 1**(원문 파서로 확인). 나머지 4사는 1000000.
  - KB금융은 매출액 대신 **순이자이익**(D-015).
- `notebooks/verify.ipynb` 실행 → 목표 `{'samples': 22, 'passed': 22, 'pending': 0, 'mismatch': 0}`. 불일치는 CSV를 고치지 말고 원인을 본다(입력 실수 / 판 / 진짜 불일치).
- 통과하면 `validation.md` 표의 원천 값·일치 칸을 채우고 `ROADMAP.md` Stage 1 체크.

### 2. Stage 2 결정 5개 (작업자)

`docs/stage2-decisions.md`. 판단마다 v0 숫자·선택지·AI 추천이 있다. 결정 칸을 채우고 `DECISIONS.md`에 옮긴다.

| 판단 | 핵심 |
|---|---|
| D-002 ROE | 지배/연결 짝, 기말/평균, 평균의 전기 자본 출처 |
| D-004 보완 | 로더에 접수일 칸·`as_of` 인자(백테스트용 기준 시점). 판 목록 + 바뀐 값만 저장 |
| D-005 나머지 | 표준 계정 범위(비율 입력만), 동의어 ID 묶음, 부호 규칙, 총영업이익 파생 계산 |
| D-006 | 단절 표, 경계 걸친 증감은 NaN + 사유, 개념 다른 계정은 표준 계정 분리 |
| D-007 | 단일 영업비용 회사의 판관비율, 표시 방식 구분 |

### 3. 그 밖에

- 손익 표 단위 저울(quant-wrap 1번에서 나옴): 순이익을 손익 표와 현금흐름표에서 따로 읽어 다르면 멈추는 검사. 지금은 손익 표 단위가 틀려도(백만 배) 잡는 검사가 없다.

- 양방향 계정 부호(2026-10-08): KB 2015~2022 부호 뒤집은 131행 중 29행이 손익·증감 계정이라 이익/손실 방향이 틀렸을 수 있다. D-005 부호 규칙 결정 때 같이 본다(`stage2-decisions.md` D-005 3번).
- forge-quant 플러그인 확인: `claude plugin list --json` (ROADMAP Stage 1 마지막 줄).
- `/quant-wrap`: 원문 파서 6단계의 마지막 절차. 클라우드에는 없어 로컬에서 한다. 재료는 `.planning/research/wrap-2026-10-07.md`(이 세션의 학습·실수·판단 근거·핵심 질문).

## 이번 클라우드 세션에서 끝난 것

- Stage 1: 수집 23건, 시드 20261007 표본 22건 추출(`validation.md`). 금융지주 대체 항목 순이자이익(D-015), 영업수익 산식 식별(D-005 부분).
- 원문 파서(D-013·D-014): BS·IS·CF, 범용 층 저장, 본문 있는 판, 계정 사전·승인제 수작업 매핑(`src/fs_pipeline_dart/manual_mapping.csv`), 기준서 전환 경계 승인제(D-006 원칙). XBRL 해 금액 전액 일치(D-013 조건 충족), KB금융 2015~2022 `fs_document.parquet` 1,188행. 재현: `uv run python -m fs_pipeline_dart.mapping` (DART가 느리면 몇십 분).
- 정정 판별 측정: 정정 판 24개 중 BS·IS 숫자 변화 3개, CF만 바뀐 것 1개, 주석·규제비율만 바뀐 것 여러 개(`stage2-decisions.md` D-004).
- 상세 경과: `.planning/research/RESUME.md`, 판단: `DECISIONS.md` D-004·D-005(부분)·D-006(부분)·D-009 변경·D-013·D-014·D-015.
