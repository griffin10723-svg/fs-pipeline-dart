"""원문 재무제표 층: 문서 모델에서 연결 재무상태표를 찾아 D-011 스키마로 낸다 (D-014 2단계).

계정 ID는 여기서 붙이지 않는다(전부 `-표준계정코드 미사용-`). ID는 mapping.py가 XBRL 짝짓기 사전으로 붙인다.
"""

import io
import re
import zipfile

import pandas as pd

from docparse.dart_xml import read_xml
from docparse.model import Document, Table
from docparse.units import parse_unit, to_won
from fs_pipeline_dart.dart import ANNUAL
from fs_pipeline_dart.document import BODY_MARK
from fs_pipeline_dart.validate import NO_ID

TOTALS = ("자산총계", "부채총계", "자본총계")
_PERIOD = re.compile(r"제\s*(\d+)")
_NOTE = re.compile(r"\(\s*주(석)?[\s\d,.\-~및]*\)$")  # 끝의 '(주석4,6)' '(주29)'
_KO = "가나다라마바사아자차카타파하"  # 번호로 쓰는 글자만. [가-하]는 거의 모든 음절이라 '자산총계'의 '자'를 먹는다
_NUMBERING = re.compile(rf"^(?:(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]+|[IVXL]+|\d+|[{_KO}])\.|\((?:\d+|[{_KO}])\))")

COLUMNS = ["corp_code", "fiscal_year", "sj_div", "account_id", "ord", "account_nm", "account_detail",
           "amount", "currency", "rcept_no", "reprt_code", "source"]


class StatementError(Exception):
    """재무제표 표를 하나로 특정하지 못했거나, 읽은 값이 항등식·핵심 계정 검사를 통과하지 못했다."""


def norm(name: str) -> str:
    """계정명 정규화 (D-014): 공백, 앞 번호(Ⅰ. XII. 1. 가. (1)), 끝 주석번호를 뗀다. 그 밖의 글자는 그대로."""
    s = re.sub(r"\s+", "", name)
    s = _NUMBERING.sub("", s)
    return _NOTE.sub("", s)


def body_document(data: bytes, rcept_no: str) -> Document:
    """zip에서 사업보고서 본문 xml 하나를 읽는다. 감사보고서(첨부)는 쓰지 않는다."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = [n for n in zf.namelist() if BODY_MARK.search(zf.read(n)[:2000])]
        if len(names) != 1:
            raise StatementError(f"{rcept_no}: 본문 xml이 {len(names)}개")
        return read_xml(zf.read(names[0]), f"{rcept_no}/{names[0].lstrip('/')}")


def _labels(t: Table) -> set[str]:
    return {norm(r[0].text) for r in t.rows if r}


def find_bs(doc: Document) -> Table:
    """연결 재무상태표 1개. 아니면 예외.

    섹션 경로에 '연결재무제표' 또는 '연결재무상태표'가 있고(주석 제외) 자산·부채·자본총계 행을 모두 가진 표.
    섹션 제목만으로는 같은 섹션의 머리 표·단위 표·손익 표가 함께 남아 총계 행을 둘째 조건으로 둔다.
    """
    def in_section(t: Table) -> bool:
        return any(("연결재무제표" in (s := re.sub(r"\s+", "", x)) or "연결재무상태표" in s) and "주석" not in s
                   for x in t.section)

    cands = [t for t in doc.tables if in_section(t) and set(TOTALS) <= _labels(t)]
    if len(cands) != 1:
        raise StatementError(f"{doc.source}: 연결 재무상태표 후보 {len(cands)}개 {[t.index for t in cands]}")
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


def parse_bs(t: Table, corp_code: str, year: int, rcept_no: str, period: int = 0) -> pd.DataFrame:
    """재무상태표 표 → D-011 행. 한 행에 그 기간 값이 두 칸 다 차 있으면 예외.

    로더는 당기(period=0)만 낸다. 전기(period=1)는 다음 해 보고서와 잇는 내부 대조용이다 (D-014).
    """
    if t.unit_text is None:
        raise StatementError(f"표 {t.index}: 단위 표기가 없다")
    unit = parse_unit(t.unit_text)
    grid = t.grid()
    cols = current_columns(grid[0], period)
    rows = []
    for ord_, r in enumerate(grid[1:], start=1):
        vals = [r[c] for c in cols if r[c].strip() not in ("",)]
        # colspan으로 펼친 같은 글자는 한 값이다
        vals = list(dict.fromkeys(vals))
        if len(vals) > 1:
            raise StatementError(f"표 {t.index} {r[0]!r}: 당기 값이 {vals}")
        rows.append({
            "corp_code": corp_code, "fiscal_year": year, "sj_div": "BS", "account_id": NO_ID,
            "ord": ord_, "account_nm": r[0].strip(), "account_detail": "-",
            "amount": to_won(vals[0], unit) if vals else None,
            "currency": "KRW", "rcept_no": rcept_no, "reprt_code": ANNUAL, "source": "document",
        })
    out = pd.DataFrame(rows, columns=COLUMNS).astype({"amount": "Int64", "ord": int, "fiscal_year": int})
    check_bs(out, unit)
    return out


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


def read_bs(data: bytes, corp_code: str, year: int, rcept_no: str) -> pd.DataFrame:
    """원문 zip → 연결 재무상태표 D-011 행 (source=document)."""
    return parse_bs(find_bs(body_document(data, rcept_no)), corp_code, year, rcept_no)
