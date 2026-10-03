# 조사 재개 메모 (2026-10-04 중단)

주간 사용 한도 때문에 `/gsd-new-project` 도중에 멈췄다. 재개 예정: 주간 한도가 초기화되는 금요일.

## 상태

- 완료: `PROJECT.md`(3af1f13), `config.json`(7cb24b8, granularity standard, 저장된 기본값 그대로)
- 남음: 조사 → `REQUIREMENTS.md` → `ROADMAP.md`·`STATE.md` → 지침 파일
- 작업자 선택: **Research first**

## 재개 방법

- `/gsd-new-project`를 다시 실행하면 중단된 초기화를 이어 가지만 `REQUIREMENTS.md`부터 시작해 조사를 건너뛴다. 그래서 재개 때는 먼저 아래 조사 설계대로 조사를 돌리고, 끝나면 요구사항 정의로 넘어간다.
- 지침 파일 단계: `generate-claude-md`가 `.claude/CLAUDE.md`를 새로 만든다. 이 레포에는 루트 `CLAUDE.md`가 따로 있고 Stage 1 세션도 이 레포에서 돈다. 만들기 전에 작업자에게 확인한다.

## 조사 설계

0. **표본 원문 받기** (scratchpad에 저장, 커밋 안 함)
   - `dart.last_rcept_no`로 접수번호를 얻고 `document.xml` API로 zip을 받는다.
   - 대상: KB금융 `00688996` 2015·2017·2019·2021·2022·2023, 삼성전자 `00126380` 2023.
   - 문서마다 기록: zip 구성, 인코딩 선언, `xml.etree` 파싱 성공 여부, 태그 종류, 섹션 제목, '연결재무상태표' 위치와 개수, 단위 표기.
   - 결과는 `.planning/research/SAMPLES.md`에 쓴다.
1. **조사 4개** (`gsd-project-researcher`가 `SAMPLES.md`를 읽고 시작)
   - STACK
     - XML 파서 선택(stdlib / lxml recover / bs4)과 형식 규칙 위반 대응
     - `uv_build`로 패키지 2개 담기(`module-name` 목록)
     - pandas 3 문자열 dtype과 `to_frame` 스키마
   - FEATURES — 재무제표 표 파서의 필수 기능
     - 단위 환산
     - 음수 표기(괄호, △)
     - 병합 셀, 다단 헤더
     - 당기·전기 열 식별
     - 계정명 정규화(로마숫자, 주석번호)
     - 섹션 경로, 주석 원표
   - ARCHITECTURE
     - DART XML(dart4.xsd)의 요소 구조
     - `dart-fss`가 표를 찾는 방식(참고만)
     - 층 사이의 경계와 만드는 순서: 리더 → 문서 모델 → 표 추출 → 재무제표 층 → 계정 매핑
   - PITFALLS — 각 함정을 어느 phase에서 다룰지 함께 적는다
     - 연도별 형식 변화(2015~2018), 인코딩
     - 감사보고서·요약재무정보와 겹치는 표
     - 금융업 BS·IS 배치, 재작성 3열
     - 같은 금액끼리 짝짓기가 충돌하는 경우
     - XBRL(원 단위)과 원문(백만원 단위)의 반올림 차이
2. **반박 검증** (조사 결과마다 1명): 위험이 큰 주장을 표본 원문과 공식 문서로 반박해 본다. 틀린 주장은 본문을 고치고 "검증 기록" 절을 덧붙인다.
3. **요약** (`gsd-research-synthesizer`) → `SUMMARY.md`. 커밋은 오케스트레이터가 한다.
