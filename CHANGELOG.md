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
