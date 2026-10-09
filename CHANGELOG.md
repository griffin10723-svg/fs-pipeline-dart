# 변경 기록

형식: [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/). 버전은 [SemVer](https://semver.org/lang/ko/)를 따른다.
Stage 게이트를 통과할 때마다 한 묶음으로 정리한다. 커밋 하나하나는 git log에 있다.

## [Unreleased]

### 추가
- Stage 0 스코프: 성공 기준(표본 20건 원문 100% 일치), Must·Should·Won't, 표본 단위 (2026-10-02 게이트 충족)
- README 첫 판: 문제 정의·성공 기준
- 판단 기록: 연결재무제표 기준(D-001), ROE 범위 일치 원칙(D-002)
- 레포 문서 5종: ROADMAP · ARCHITECTURE · CHANGELOG · DECISIONS
- 착수 전 원문 대조 기록(3개사 2024, 9개 값)을 `docs/validation.md`로 이관. Stage 1 착수 (2026-10-03)
- 표본 추출·대조 판정 도구 `sample.py` + `notebooks/verify.ipynb` (Stage 1 게이트용, 2026-10-07)
- Stage 1 수집 확장: 비금융 4사 2021~2025 + KB금융 2023~2025, 시드 20261007 표본 22건 추출. 금융지주 표본은 순이자이익 대조(D-015), 매출 태그 없는 영업수익 형식은 산식 식별(D-005 부분) (2026-10-07)
- Stage 1 원문 대조 완료: 22건(무작위 20 + 경계 2: KB금융 2024 정정본·카카오 2023) 66개 값 정확 일치, 불일치 0 (2026-10-09)
- 원문 파서 (D-013·D-014, 2026-10-07)
  - `docparse`: DART 원문 리더(stdlib html.parser, CP949 대체), 문단·표·셀 parquet 저장
  - `document`: 본문을 가진 마지막 판 받기([첨부정정]·014 건너뜀)
  - `statement`: 연결 재무상태표·손익 표 특정과 파싱, 항등식·당기순이익 검사
  - `mapping`: 금액 짝짓기 계정 사전, 최근 연도 ID·부호, 다음 해 전기 금액 잇기, 승인제 수작업 매핑, 한 해 빼기 XBRL 대조
  - KB금융 2015~2022 연결 BS·IS·CF 1,188행(`fs_document.parquet`). CF는 D-014 범위 변경으로 추가, SCE는 보류. XBRL 해 금액 753행 전액 일치, dart-fss 보조 대조

### 바뀜
- XBRL 행에 `source=xbrl` 칸 (D-014)
- 금융업 2022 이전 Won't 해제 (D-009 변경)
