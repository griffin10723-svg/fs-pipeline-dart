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

### XBRL 없는 해 (금융업 2022 이전, D-013·D-014)

```
OpenDART document.xml (사업보고서 원문 zip, 본문을 가진 마지막 판)
   │  docparse.dart_xml: 형식 중립 문서 모델(섹션 경로·문단·표·단위)
   ├─▶ docparse.store: 문단·표·셀 parquet (data/processed/document/{접수번호}/) — 주석 표·본문 재사용
   │  statement: 연결 BS·IS 표 1개 특정 → D-011 행(source=document), 항등식 검사
   ▼
mapping: 같은 공시 XBRL과 금액 짝짓기 → 계정명→ID 사전(+승인 수작업)
   │  XBRL 없는 해: 다음 해 전기 금액으로 ID를 잇고 값은 그해 원래 값 (D-005 부분)
   ▼
data/processed/fs_document.parquet (XBRL parquet과 같은 스키마)
```

## 모듈 (계획)

| 경로 | 하는 일 | 입력 | 출력 |
|---|---|---|---|
| `src/…/data/collect` | DART 호출, 응답 상태 검사, 원본 JSON 저장 | 기업코드, 연도 | `data/raw/*.json` |
| `src/…/data/standardize` | 계정 식별·표준 계정 매핑 | 원본 JSON | 표준화 parquet |
| `src/…/core/ratios` | 재무비율 산출 | 표준화 parquet | 비율 표 |
| `src/fs_pipeline_dart/sample.py` | Stage 1 게이트 표본 추출(시드)·원문 대조 판정. DART 호출 없음 | `data/processed/fs_long.parquet`, 시드, 경계 사례 | `outputs/sample.csv`, `validation.md` 표 행 |
| `src/docparse/` | 형식 중립 문서 모델, DART 원문 리더, 단위 해석, parquet 저장. `fs_pipeline_dart`를 import하지 않는다(새 레포 승격 전제) | 원문 zip 바이트 | `Document`, 문단·표·셀 parquet |
| `src/fs_pipeline_dart/document.py` | 사업보고서 판 목록, 본문을 가진 마지막 판 받기(D-004) | 기업코드, 연도 | `data/raw/document/{접수번호}.zip` |
| `src/fs_pipeline_dart/statement.py` | 연결 BS·IS 표 특정과 D-011 행 변환 | `Document` | 원문 재무제표 행 |
| `src/fs_pipeline_dart/mapping.py` | 계정 사전·XBRL 대조·XBRL 없는 해 잇기. `manual_mapping.csv`는 작업자 승인 기록 | XBRL parquet·원본 JSON, 원문 | `fs_document.parquet`, `outputs/mapping/*.csv` |
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
