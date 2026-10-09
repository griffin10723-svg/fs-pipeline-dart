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
    ("XⅢ. 당기순이익", "당기순이익"),  # KB금융 2020·2021: 라틴 X + 로마 숫자 Ⅲ
    ("가. 매출채권", "매출채권"),
    ("(1) 기타", "기타"),
    ("현금및현금성자산 (주4,28)", "현금및현금성자산"),
    ("매출채권(순액)", "매출채권(순액)"),
])
def test_norm(raw, want):
    assert st.norm(raw) == want


def test_parse_split_columns_takes_current_period_in_won():
    df = st.parse_statement(_t(SPLIT), "BS", "00688996", 2019, "R1")
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
        st.parse_statement(_t(bad), "BS", "C", 2019, "R1")


def test_missing_unit_fails():
    with pytest.raises(st.StatementError, match="단위"):
        st.parse_statement(_t(SPLIT, unit=None), "BS", "C", 2019, "R1")


def test_find_bs_needs_exactly_one_candidate():
    head = _t([["제12기말"], ["(단위: 백만원)"]], index=0)
    bs = _t(SPLIT, index=1)
    separate = _t(SPLIT, section=("III. 재무에 관한 사항", "4. 재무제표"), index=2)
    note = _t(SPLIT, section=("III. 재무에 관한 사항", "3. 연결재무제표 주석"), index=3)
    assert st.find_statement(Document("x", tables=[head, bs, separate, note]), "BS").index == 1
    with pytest.raises(st.StatementError, match="후보 2개"):
        st.find_statement(Document("x", tables=[bs, _t(SPLIT, index=4)]), "BS")


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


IS_ROWS = [
    ["과 목", "제 8(당) 기", "제 7(전) 기"],
    ["Ⅰ. 영업이익", "100", "90"],
    ["XⅢ. 당기순이익", "70", "60"],
    ["XⅣ. 총포괄이익", "75", "61"],
    ["기본주당이익 (단위 : 원)", "4,396원", "(2,315.0)"],
]


def test_parse_income_statement_cis_and_per_share():
    df = st.parse_statement(_t(IS_ROWS), "IS", "C", 2015, "R1")
    assert set(df["sj_div"]) == {"CIS"}  # 총포괄 행이 있으면 단일 포괄손익계산서
    assert df["amount"].tolist() == [100 * 10**6, 70 * 10**6, 75 * 10**6, 4396]
    prior = st.parse_statement(_t(IS_ROWS), "IS", "C", 2014, "R1", period=1)
    assert prior["amount"].tolist()[-1] == -2315


def test_per_share_fraction_fails():
    rows = [r[:] for r in IS_ROWS]
    rows[4][1] = "4,396.5"
    with pytest.raises(st.StatementError, match="소수"):
        st.parse_statement(_t(rows), "IS", "C", 2015, "R1")


def test_income_statement_without_net_income_fails():
    rows = [r for r in IS_ROWS if "당기순이익" not in r[0]] + [["계속영업당기순이익", "1", "1"]]
    with pytest.raises(st.StatementError, match="당기순이익"):
        st.parse_statement(_t(rows), "IS", "C", 2015, "R1")


def test_dash_in_split_column_is_empty_side():
    # 리뷰: 나눠진 두 칸 중 한쪽이 '-'면 빈 칸으로 본다
    rows = [r[:] for r in SPLIT]
    rows[2] = ["Ⅰ. 현금 및 예치금", "-", "20", "", ""]
    df = st.parse_statement(_t(rows), "BS", "C", 2019, "R1")
    assert df["amount"].iloc[1] == 20 * 10**6


def test_loss_year_income_statement_found():
    # 리뷰: '영업손실'·'당기순손실'만 있는 해도 손익 표로 잡는다
    loss = _t([["과 목", "제 3 기"], ["영업손실", "(5)"], ["당기순손실", "(7)"]])
    assert st.find_statement(Document("x", tables=[loss]), "IS") is loss


def test_rcept_no_format_checked_before_file_name():
    with pytest.raises(ValueError, match="접수번호"):
        d._download("../../etc/passwd")


def test_oversized_xml_member_rejected(monkeypatch):
    from docparse import dart_xml
    monkeypatch.setattr(dart_xml, "MAX_XML", 10)
    with pytest.raises(ValueError, match="상한"):
        d.body_xml(_zip([("R1.xml", "11011")]))


def test_cash_flow_statement_is_not_income_candidate():
    # 한전 2022: 같은 섹션의 현금흐름표도 당기순이익·영업 행을 가진다
    income = _t([["과 목", "제 62 기"], ["영업이익(손실)", "(32,655,153)"], ["당기순이익(손실)", "(24,429,108)"]], index=0)
    cash = _t([["과 목", "제 62 기"], ["영업활동현금흐름", "(23,477,500)"], ["당기순이익(손실)", "(24,429,108)"],
               ["영업이익 조정", "1"]], index=1)
    assert st.find_statement(Document("x", tables=[income, cash]), "IS") is income


def test_per_share_won_per_share_suffix():
    rows = [r[:] for r in IS_ROWS]
    rows[4][1] = "(2,315)원/주"
    assert st.parse_statement(_t(rows), "IS", "C", 2015, "R1")["amount"].iloc[-1] == -2315


def test_cash_flow_hedge_row_keeps_income_candidate():
    # 회귀: 포괄손익의 '현금흐름위험회피' 행 때문에 손익 표가 빠지던 것 (KB·한전)
    cis = _t([["과 목", "제 62 기"], ["영업이익", "10"], ["당기순이익", "7"], ["현금흐름위험회피", "1"]])
    assert st.find_statement(Document("x", tables=[cis]), "IS") is cis


CF_ROWS = [
    ["과 목", "제 16 기", "제 15 기"],
    ["Ⅰ. 영업활동으로 인한 현금흐름", "4,110", "5,690"],
    ["Ⅱ. 투자활동으로 인한 현금흐름", "(1,000)", "(900)"],
    ["Ⅳ. 기말의 현금및현금성자산", "29,836", "32,474"],
]


def test_cash_flow_statement_found_under_its_own_title():
    # 2023년 이후 형식: '2-4. 연결 현금흐름표' 섹션. '계산서'가 없어도 연결재무제표 섹션으로 본다
    cf = _t(CF_ROWS, section=("III. 재무에 관한 사항", "2-4. 연결 현금흐름표"))
    note = _t(CF_ROWS, section=("III. 재무에 관한 사항", "3. 연결재무제표 주석"), index=1)
    assert st.find_statement(Document("x", tables=[cf, note]), "CF") is cf
    df = st.parse_statement(cf, "CF", "C", 2023, "R1")
    assert set(df["sj_div"]) == {"CF"} and df["amount"].tolist()[:2] == [4110 * 10**6, -1000 * 10**6]


def test_cash_flow_without_operating_total_fails():
    df = st.pd.DataFrame({"account_nm": ["Ⅱ. 투자활동으로 인한 현금흐름", "영업활동 조정"], "amount": [1, 1]})
    with pytest.raises(st.StatementError, match="영업활동"):
        st.check_cf(df)


class _Resp:
    def __init__(self, content):
        self.content = content


def test_download_reports_dart_maintenance(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "RAW_DOC", tmp_path)
    body = ('<?xml version="1.0" encoding="UTF-8"?><result><status>800</status>'
            '<message>시스템 점검으로 인한  서비스가 중지 중입니다.</message></result>').encode()
    monkeypatch.setattr(d.dart, "_get", lambda *a, **k: _Resp(body))
    with pytest.raises(d.DartUnavailable, match="status 800 시스템 점검"):
        d._download("20240312000736")
    assert not list(tmp_path.iterdir())  # 오류 응답을 원본으로 저장하지 않는다
