"""원문 재무상태표 층: 표 특정·당기 열·단위 환산·항등식 검사가 0단계에서 본 형식을 따른다."""

import io
import zipfile

import pytest

from docparse.model import Cell, Document, Table
from fs_pipeline_dart import document as d
from fs_pipeline_dart import statement as st

SEC = ("III. 재무에 관한 사항", "2. 연결재무제표")


def _t(rows, section=SEC, unit="(단위 : 백만원)", index=0):
    return Table(section=section, rows=[[Cell(x) for x in r] for r in rows], unit_text=unit, index=index)


# KB금융 2017~2022 형식: 기마다 금액·소계 두 칸
SPLIT = [
    ["과 목", "제12기말", "제12기말", "제11기말", "제11기말"],
    ["자 산", "", "", "", ""],
    ["Ⅰ. 현금 및 예치금 (주석4,6)", "20", "", "19", ""],
    ["자 산 총 계", "", "100", "", "90"],
    ["부 채 총 계", "", "70", "", "60"],
    ["자 본 총 계", "", "30", "", "30"],
]


@pytest.mark.parametrize("raw, want", [
    ("자 산 총 계", "자산총계"),  # '자'는 번호가 아니다
    ("Ⅰ. 현금 및 예치금 (주석4,6,7,8,39)", "현금및예치금"),
    ("1. 현금및현금성자산", "현금및현금성자산"),
    ("XII. 이연법인세자산", "이연법인세자산"),  # KB금융 2022: Ⅻ 대신 라틴 문자
    ("Ⅻ. 기타자산", "기타자산"),
    ("가. 매출채권", "매출채권"),
    ("(1) 기타", "기타"),
    ("현금및현금성자산 (주4,28)", "현금및현금성자산"),
    ("매출채권(순액)", "매출채권(순액)"),
])
def test_norm(raw, want):
    assert st.norm(raw) == want


def test_parse_split_columns_takes_current_period_in_won():
    df = st.parse_bs(_t(SPLIT), "00688996", 2019, "R1")
    assert df["amount"].isna().iloc[0]  # '자 산' 머리 행은 금액이 없다
    assert df["amount"].tolist()[1:3] == [20 * 10**6, 100 * 10**6]
    assert set(df["source"]) == {"document"} and set(df["account_id"]) == {st.NO_ID}
    assert df.columns.tolist() == st.COLUMNS


def test_current_period_is_largest_number_not_leftmost():
    assert st.current_columns(["", "제 54 기", "제 55 기"]) == [2]


def test_identity_off_by_more_than_one_unit_fails():
    bad = [r[:] for r in SPLIT]
    bad[5][2] = "28"
    with pytest.raises(st.StatementError, match="자산 - 부채 - 자본"):
        st.parse_bs(_t(bad), "C", 2019, "R1")


def test_missing_unit_fails():
    with pytest.raises(st.StatementError, match="단위"):
        st.parse_bs(_t(SPLIT, unit=None), "C", 2019, "R1")


def test_find_bs_needs_exactly_one_candidate():
    head = _t([["제12기말"], ["(단위: 백만원)"]], index=0)
    bs = _t(SPLIT, index=1)
    separate = _t(SPLIT, section=("III. 재무에 관한 사항", "4. 재무제표"), index=2)
    note = _t(SPLIT, section=("III. 재무에 관한 사항", "3. 연결재무제표 주석"), index=3)
    assert st.find_bs(Document("x", tables=[head, bs, separate, note])).index == 1
    with pytest.raises(st.StatementError, match="후보 2개"):
        st.find_bs(Document("x", tables=[bs, _t(SPLIT, index=4)]))


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, acode in files:
            zf.writestr(name, f'<?xml version="1.0"?><DOCUMENT><DOCUMENT-NAME ACODE="{acode}">x</DOCUMENT-NAME>'
                              "</DOCUMENT>".encode())
    return buf.getvalue()


def test_fetch_document_skips_attachment_only_correction(monkeypatch):
    # D-004: [첨부정정]은 감사보고서만 담는다. 본문을 가진 마지막 판으로 내려간다 (KB금융 2015)
    zips = {"20160401000506": _zip([("/20160401000506_00760.xml", "00760"), ("/20160401000506_00761.xml", "00761")]),
            "20160330004428": _zip([("20160330004428.xml", "11011"), ("20160330004428_00761.xml", "00761")])}
    monkeypatch.setattr(d, "report_versions", lambda c, y, f=False: ["20160401000506", "20160330004428"])
    monkeypatch.setattr(d, "_download", zips.__getitem__)
    rcept, data = d.fetch_document("00688996", 2015)
    assert rcept == "20160330004428" and data == zips[rcept]


def test_fetch_document_without_any_body_fails(monkeypatch):
    monkeypatch.setattr(d, "report_versions", lambda c, y, f=False: ["R1"])
    monkeypatch.setattr(d, "_download", lambda r: _zip([("R1_00760.xml", "00760")]))
    with pytest.raises(RuntimeError, match="본문을 가진 판이 없다"):
        d.fetch_document("C", 2015)


def test_fetch_document_skips_version_without_file(monkeypatch):
    # KB금융 2025: 마지막 정정 판은 document.xml이 014(파일 없음)
    body = _zip([("R1.xml", "11011")])
    monkeypatch.setattr(d, "report_versions", lambda c, y, f=False: ["R2", "R1"])
    monkeypatch.setattr(d, "_download", {"R2": None, "R1": body}.__getitem__)
    assert d.fetch_document("00688996", 2025) == ("R1", body)
