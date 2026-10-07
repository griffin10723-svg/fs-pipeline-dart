"""DART 원문 리더: 0단계에서 본 함정(거짓 utf-8 선언·이스케이프 없는 &·<·앞 표의 단위)을 합성 문서로 고정한다."""

import io
import zipfile

from docparse.dart_xml import decode, read_xml, read_zip
from docparse.units import parse_unit

DOC = """<?xml version="1.0" encoding="utf-8"?>
<DOCUMENT>
<DOCUMENT-NAME ACODE="11011">사업보고서</DOCUMENT-NAME>
<BODY>
<SECTION-1><TITLE ATOC="Y">III. 재무에 관한 사항</TITLE>
<SECTION-2><TITLE ATOC="Y">2. 연결재무제표</TITLE>
<P>가. 연결대차대조표(재무상태표)</P>
<P>주1)< 정정 전 > R&D 비용&cr;포함</P>
<TABLE><TR><TD>주식회사 KB금융지주와 그 종속기업</TD><TD>(단위: 백만원)</TD></TR></TABLE>
<TABLE>
<TR><TH ROWSPAN="2">과 목</TH><TH COLSPAN="2">제 15기말</TH></TR>
<TR><TH>금액</TH><TH>주석</TH></TR>
<TR><TE>자산총계</TE><TE>701,170,848</TE><TE>5</TE></TR>
</TABLE>
</SECTION-2>
<SECTION-2><TITLE ATOC="Y">3. 연결재무제표 주석</TITLE>
<TABLE><TR><TD>바깥<TABLE><TR><TD>안쪽</TD></TR></TABLE></TD></TR></TABLE>
</SECTION-2>
</SECTION-1>
</BODY>
</DOCUMENT>
"""


def test_false_utf8_declaration_falls_back_to_cp949():
    raw = DOC.encode("cp949")
    assert b'encoding="utf-8"' in raw
    assert decode(raw) == DOC


def test_sections_paragraphs_and_lenient_markup():
    doc = read_xml(DOC.encode("cp949"), "test")
    sec = ("III. 재무에 관한 사항", "2. 연결재무제표")
    assert [p.text for p in doc.paragraphs] == ["가. 연결대차대조표(재무상태표)", "주1)< 정정 전 > R&D 비용 포함"]
    assert all(p.section == sec for p in doc.paragraphs)
    assert doc.tables[1].section == sec


def test_statement_table_grid_and_unit_from_previous_table():
    t = read_xml(DOC.encode(), "test").tables[1]
    assert t.grid() == [
        ["과 목", "제 15기말", "제 15기말"],
        ["과 목", "금액", "주석"],
        ["자산총계", "701,170,848", "5"],
    ]
    assert t.rows[0][0].header and not t.rows[2][0].header
    assert parse_unit(t.unit_text) == 10**6


def test_unit_not_inherited_across_sections():
    doc = read_xml(DOC.encode(), "test")
    assert all(t.unit_text is None for t in doc.tables if t.section[-1] == "3. 연결재무제표 주석")


def test_nested_table_is_its_own_table():
    doc = read_xml(DOC.encode(), "test")
    inner, outer = doc.tables[2], doc.tables[3]
    assert inner.grid() == [["안쪽"]]
    assert outer.grid() == [["바깥"]]
    assert [t.index for t in doc.tables] == [0, 1, 2, 3]


def test_zip_with_main_and_audit_report():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("/20231005000471.xml", DOC.encode())
        zf.writestr("20231005000471_00761.xml", DOC.encode("cp949"))
    docs = read_zip(buf.getvalue(), "20231005000471")
    assert sorted(docs) == ["20231005000471.xml", "20231005000471_00761.xml"]
    assert docs["20231005000471.xml"].source == "20231005000471/20231005000471.xml"


def test_unit_in_data_row_label_is_not_table_unit():
    # 삼성전자 2024 손익 표: 표 안 단위는 주당이익 행 머리뿐, 표 단위(백만원)는 바로 앞 문단
    doc = read_xml("""<SECTION-1><TITLE>2-2. 연결 손익계산서</TITLE><P>(단위 : 백만원)</P>
<TABLE><TR><TD></TD><TD>제 56 기</TD></TR><TR><TD>매출액</TD><TD>300,870,903</TD></TR>
<TR><TD>기본주당이익 (단위 : 원)</TD><TD>4,950</TD></TR></TABLE></SECTION-1>""".encode(), "t")
    assert parse_unit(doc.tables[0].unit_text) == 10**6


def test_unclosed_tr_keeps_previous_row():
    # 리뷰: </TR> 없이 다음 <TR>이 열리면 앞 행을 버리던 문제
    doc = read_xml(b"<TABLE><TR><TD>a</TD><TD>1</TD><TR><TD>b</TD><TD>2</TD></TABLE>", "t")
    assert doc.tables[0].grid() == [["a", "1"], ["b", "2"]]
