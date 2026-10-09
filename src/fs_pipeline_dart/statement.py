"""원문 재무제표 층: 문서 모델에서 연결 재무상태표를 찾아 D-011 스키마로 낸다 (D-014 2단계).

계정 ID는 여기서 붙이지 않는다(전부 `-표준계정코드 미사용-`). ID는 mapping.py가 XBRL 짝짓기 사전으로 붙인다.
"""

import re

import pandas as pd

from docparse.dart_xml import read_xml
from docparse.model import Document, Table
from docparse.units import parse_unit, to_won
from fs_pipeline_dart.dart import ANNUAL
from fs_pipeline_dart.document import body_xml
from fs_pipeline_dart.rowlog import rows_logged
from fs_pipeline_dart.validate import NO_ID, display_unit

TOTALS = ("자산총계", "부채총계", "자본총계")
# 당기순이익·당기순손실·당기순손익·연결당기순이익(손실). '계속영업당기순이익'·'지배기업…귀속'은 아니다
NET_INCOME = re.compile(r"^(연결)?당기순(이익|손실|손익)(\(손실\))?$")
_UNIT_IN_LABEL = re.compile(r"\(\s*단\s*위\s*[:：]?[^)]*\)")
_PERIOD = re.compile(r"제\s*(\d+)")
_UNIT_SUFFIX = re.compile(r"\((단위:)?(원|백만원|천원)\)$")
_NOTE = re.compile(r"\(\s*주(석)?[\s\d,.\-~및]*\)$")  # 끝의 '(주석4,6)' '(주29)'
_KO = "가나다라마바사아자차카타파하"  # 번호로 쓰는 글자만. [가-하]는 거의 모든 음절이라 '자산총계'의 '자'를 먹는다
_NUMBERING = re.compile(rf"^(?:(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫIVXL]+|\d+|[{_KO}])\.|\((?:\d+|[{_KO}])\))")

COLUMNS = ["corp_code", "fiscal_year", "sj_div", "account_id", "ord", "account_nm", "account_detail",
           "amount", "currency", "rcept_no", "reprt_code", "source"]


class StatementError(Exception):
    """재무제표 표를 하나로 특정하지 못했거나, 읽은 값이 항등식·핵심 계정 검사를 통과하지 못했다."""


def norm(name: str) -> str:
    """계정명 정규화 (D-014): 공백, 앞 번호(Ⅰ. XII. 1. 가. (1)), 끝 주석번호·단위 표기를 뗀다. 그 밖의 글자는 그대로."""
    s = re.sub(r"\s+", "", name)
    s = _NUMBERING.sub("", s)
    s = _NOTE.sub("", s)
    return _UNIT_SUFFIX.sub("", s)  # '기본주당이익(단위:원)'·'기본주당이익(원)'의 단위 표기


def body_document(data: bytes, rcept_no: str) -> Document:
    """zip에서 사업보고서 본문 xml 하나를 읽는다. 감사보고서(첨부)는 쓰지 않는다."""
    body = body_xml(data)
    if body is None:
        raise StatementError(f"{rcept_no}: 본문 xml이 없다")
    return read_xml(body[1], f"{rcept_no}/{body[0]}")


def _labels(t: Table) -> set[str]:
    return {norm(r[0].text) for r in t.rows if r}


def _in_section(t: Table) -> bool:
    """섹션 경로에 '연결재무제표' 또는 '연결 ○○표/계산서'(주석 제외).

    2023년 이후 형식은 '2-4. 연결 현금흐름표'처럼 표마다 제목이 따로 있다.
    """
    for x in t.section:
        s = re.sub(r"\s+", "", x)
        if "주석" not in s and ("연결재무제표" in s or "연결재무상태표" in s
                               or ("연결" in s and ("계산서" in s or "현금흐름표" in s))):
            return True
    return False


def _has_income_rows(labels: set[str]) -> bool:
    # 현금흐름표도 당기순이익·영업 행을 가진다(한전 2022, 재무제표가 한 섹션에 모인 형식)
    # '현금흐름'으로 거르면 포괄손익의 '현금흐름위험회피' 행까지 걸린다. 현금흐름표만의 '영업활동'으로 가른다
    if any("영업활동" in x for x in labels):
        return False
    op = any(re.search(r"영업(이익|손익|손실)", x) for x in labels)
    net = any(re.search(r"당기순(이익|손익|손실)", x) for x in labels)
    return op and net


def find_statement(doc: Document, kind: str) -> Table:
    """연결 재무상태표(BS) 또는 손익(IS) 표 1개. 아니면 예외 (D-014 변경 2026-10-07).

    섹션 제목만으로는 같은 섹션의 머리 표·단위 표·다른 재무제표가 함께 남아 내용 조건을 둔다.
    - BS: 자산·부채·자본총계 행을 모두 가진 표
    - IS: 영업이익(손익)·당기순이익(손익) 행을 모두 가진 표. 손익과 포괄손익을 따로 내면 손익계산서만 잡힌다
    - CF: 영업활동 행과 기말 현금 행을 가진 표 (D-014 범위 변경 2026-10-07)
    문단 소제목은 쓰지 않는다. KB금융 2015·2018은 손익 표 앞 문단이 '가. 연결대차대조표'다.
    """
    if kind == "BS":
        def ok(t):
            return set(TOTALS) <= _labels(t)
    elif kind == "CF":
        def ok(t):
            labels = _labels(t)
            return any("영업활동" in x for x in labels) and any("기말" in x and "현금" in x for x in labels)
    elif kind == "IS":
        def ok(t):
            return _has_income_rows(_labels(t))
    else:
        raise ValueError(kind)
    cands = [t for t in doc.tables if _in_section(t) and ok(t)]
    if len(cands) != 1:
        raise StatementError(f"{doc.source}: 연결 {kind} 후보 {len(cands)}개 {[t.index for t in cands]}")
    return cands[0]


def current_columns(header: list[str], period: int = 0) -> list[int]:
    """머리 행에서 기간 열. period 0 = 당기('제 N 기' 숫자가 가장 큰 열들), 1 = 전기.

    금액·소계 두 칸으로 나뉘면 둘 다 낸다.
    """
    nums = {i: int(m.group(1)) for i, h in enumerate(header) if (m := _PERIOD.search(h))}
    ranks = sorted(set(nums.values()), reverse=True)
    if len(ranks) <= period:
        raise StatementError(f"머리 행에 {period}번째 기간이 없다: {header}")
    return [i for i, n in nums.items() if n == ranks[period]]


@rows_logged
def parse_statement(t: Table, kind: str, corp_code: str, year: int, rcept_no: str, period: int = 0) -> pd.DataFrame:
    """재무제표 표 → D-011 행. 한 행에 그 기간 값이 두 칸 다 차 있으면 예외.

    로더는 당기(period=0)만 낸다. 전기(period=1)는 다음 해 보고서와 잇는 내부 대조용이다 (D-014).
    손익 표에 총포괄 행이 있으면 단일 포괄손익계산서로 보고 sj_div를 CIS로 둔다(XBRL과 같은 구분).
    """
    if t.unit_text is None:
        raise StatementError(f"표 {t.index}: 단위 표기가 없다")
    unit = parse_unit(t.unit_text)
    grid = t.grid()
    cols = current_columns(grid[0], period)
    if kind in ("BS", "CF"):
        sj = kind
    else:
        sj = "CIS" if any("총포괄" in x for x in _labels(t)) else "IS"
    rows = []
    for ord_, r in enumerate(grid[1:], start=1):
        vals = [r[c] for c in cols if r[c].strip() not in ("", "-", "–", "—")]  # 나눠진 두 칸 중 빈 쪽
        # colspan으로 펼친 같은 글자는 한 값이다
        vals = list(dict.fromkeys(vals))
        if len(vals) > 1:
            raise StatementError(f"표 {t.index} {r[0]!r}: 당기 값이 {vals}")
        rows.append({
            "corp_code": corp_code, "fiscal_year": year, "sj_div": sj, "account_id": NO_ID,
            "ord": ord_, "account_nm": r[0].strip(), "account_detail": "-",
            "amount": (_per_share(vals[0], r[0]) if "주당" in r[0] else to_won(vals[0], unit)) if vals else None,
            "currency": "KRW", "rcept_no": rcept_no, "reprt_code": ANNUAL, "source": "document",
        })
    out = pd.DataFrame(rows, columns=COLUMNS).astype({"amount": "Int64", "ord": int, "fiscal_year": int})
    {"BS": lambda: check_bs(out, unit), "IS": lambda: check_is(out), "CF": lambda: check_cf(out)}[kind]()
    return out


def check_cf(df: pd.DataFrame) -> None:
    """영업활동 현금흐름 합계 행에 값이 있어야 한다."""
    op = df.loc[df["account_nm"].map(norm).str.match(r"^영업활동(으로인한|으로부터의|)?현금흐름"), "amount"].dropna()
    if op.empty:
        raise StatementError("영업활동 현금흐름 값이 없다")


def _per_share(cell: str, label: str):
    """주당이익 행: 원 단위(행 머리에 단위가 있으면 그 단위), '4,396원'·'2,131.0'·'(2,315.0)' 형식."""
    m = _UNIT_IN_LABEL.search(label)
    mult = parse_unit(m.group(0)) if m else 1
    s = re.sub(r"\s+", "", cell).removesuffix("원/주").removesuffix("원")  # 카카오 2023 원공시 '(2,315)원/주'
    frac = re.fullmatch(r"(.*?)\.(\d+)(\)?)", s)
    if frac:
        if int(frac.group(2)):
            raise StatementError(f"주당 금액에 소수가 있다: {cell!r}")
        s = frac.group(1) + frac.group(3)
    return to_won(s, mult)


def check_is(df: pd.DataFrame) -> None:
    """핵심 계정: 당기순이익 행에 값이 있어야 한다 (D-014)."""
    names = df["account_nm"].map(norm)
    net = df.loc[names.str.match(NET_INCOME), "amount"].dropna()
    if net.empty:
        raise StatementError(f"당기순이익 값이 없다: {sorted(set(names))[:20]}")


def _net_income(df: pd.DataFrame):
    v = df.loc[df["account_nm"].map(norm).str.match(NET_INCOME), "amount"].dropna()
    return None if v.empty else int(v.iloc[0])


def check_net_income(is_df: pd.DataFrame, cf_df: pd.DataFrame) -> bool:
    """손익 표 단위 저울: 손익계산서와 현금흐름표의 당기순이익이 같아야 한다.

    두 표는 단위를 따로 읽으므로, 한쪽 단위를 잘못 읽으면(백만 배) 여기서 어긋난다.
    부호는 표시 방식(당기순손실을 양수로 적는 등)이 표마다 달라 크기만 비교한다.
    현금흐름표에 당기순이익 행이 없으면(직접법 등) False — 호출하는 쪽이 '못 잼'으로 남긴다.
    """
    a, b = _net_income(is_df), _net_income(cf_df)
    if b is None:
        return False
    if a is None:
        raise StatementError("손익 표에 당기순이익 값이 없다")
    tol = max(display_unit(is_df["amount"].dropna()), display_unit(cf_df["amount"].dropna()))
    if abs(abs(a) - abs(b)) > tol:
        raise StatementError(f"당기순이익 손익 {a:,}원 != 현금흐름 {b:,}원 (허용 ±{tol:,}) — 단위를 잘못 읽었을 수 있다")
    return True


def check_bs(df: pd.DataFrame, unit: int) -> None:
    """핵심 계정이 하나씩 있고 자산 = 부채 + 자본(표시 단위 ±1). 회계판단: validate 항등식과 같다."""
    names = df["account_nm"].map(norm)
    vals = {}
    for k in TOTALS:
        v = df.loc[names == k, "amount"].dropna()
        if len(v) != 1:
            raise StatementError(f"{k} 값이 {len(v)}개")
        vals[k] = int(v.iloc[0])
    gap = vals["자산총계"] - vals["부채총계"] - vals["자본총계"]
    if abs(gap) > unit:
        raise StatementError(f"자산 - 부채 - 자본 = {gap:,}원 (허용 ±{unit:,})")
