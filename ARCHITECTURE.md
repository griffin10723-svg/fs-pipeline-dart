# 구조 — fs-pipeline-dart

> v0 구현 전 계획이다. Stage 2를 마치면 실제 구조로 고친다.

## 데이터 흐름

```
OpenDART API (단일회사 전체 재무제표, 연결)
   │  수집: 기업 × 연도 × 사업보고서
   ▼
원본 JSON 보관 (data/raw/, 커밋하지 않음)
   │  정제: 계정 식별(표준계정ID + 재무제표 구분) → 표준 계정 매핑
   ▼
표준화 재무제표 (parquet, 기업코드 · 연도 · 표준계정 · 금액)
   │  계산
   ▼
재무비율 30종
   │
   ├─▶ 로더 함수 — 다른 레포가 import
   └─▶ analyze(subject) — 플랫폼 ⓪ 기업 개요 화면
```

## 모듈 (계획)

| 경로 | 하는 일 | 입력 | 출력 |
|---|---|---|---|
| `src/…/data/collect` | DART 호출, 응답 상태 검사, 원본 JSON 저장 | 기업코드, 연도 | `data/raw/*.json` |
| `src/…/data/standardize` | 계정 식별·표준 계정 매핑 | 원본 JSON | 표준화 parquet |
| `src/…/core/ratios` | 재무비율 산출 | 표준화 parquet | 비율 표 |
| `src/fs_pipeline_dart/sample.py` | Stage 1 게이트 표본 추출(시드)·원문 대조 판정. DART 호출 없음 | `data/processed/fs_long.parquet`, 시드, 경계 사례 | `outputs/sample.csv`, `validation.md` 표 행 |
| `src/…/loader` | 다른 레포용 읽기 함수. 없으면 수집해서 저장 | 기업코드, 연도 | DataFrame |
| `src/…/core/analyze.py` | 플랫폼 진입 함수 + `SAMPLE` | `{"kind": "company", "corp_code", "fiscal_year"}` | 5칸 dict |

## 다른 레포와의 연결

- 이 레포가 공유 데이터 레이어다. 다른 레포는 DART를 다시 호출하지 않고 로더를 import한다.
- 로더의 이름과 반환 형식(기업코드 · 연도 · 표준계정)은 v0부터 바꾸지 않는다.
- 플랫폼(P8) 단계에서 DuckDB로 옮긴다. 로더는 DuckDB에 있으면 읽고, 없으면 DART에서 받아 저장한다.

## 플랫폼 계약

`analyze()`는 `kpis`(2~4개) · `tables` · `figures` · `assumptions`(필수) · `sources`(필수)를 돌려준다.
`assumptions`에는 연결/별도 선택(D-001)·정정공시 정책(D-004)·표준화 규칙 버전(D-005), `sources`에는 DART 접수번호가 들어간다.

## 안전장치

- HTTP 상태와 DART 응답 `status`를 둘 다 검사한다 (HTTP 200이어도 `013` 등은 실패).
- 고유번호로 받은 회사가 기대한 회사인지 종목명으로 확인한다.
- merge는 `validate=`로 키 관계를 강제하고, 전후 행 수를 기록한다.
- 금액 변환 실패는 조용히 NaN으로 바꾸지 않고 멈춘다.
