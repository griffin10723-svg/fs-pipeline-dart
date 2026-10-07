"""병합 셀 펼치기: 재무제표 머리글(당기·전기 colspan, 과목 rowspan)이 격자로 맞게 풀린다."""

import pytest

from docparse.model import Cell, SpanError, expand_spans


def test_plain_rows():
    rows = [[Cell("과목"), Cell("당기")], [Cell("자산총계"), Cell("1,000")]]
    assert expand_spans(rows) == [["과목", "당기"], ["자산총계", "1,000"]]


def test_typical_fs_header():
    # | 과목(rowspan2) | 제7기(colspan2) |
    # |               | 금액 | 주석 |
    rows = [
        [Cell("과목", rowspan=2), Cell("제7기", colspan=2)],
        [Cell("금액"), Cell("주석")],
        [Cell("자산총계"), Cell("1,000"), Cell("5")],
    ]
    assert expand_spans(rows) == [
        ["과목", "제7기", "제7기"],
        ["과목", "금액", "주석"],
        ["자산총계", "1,000", "5"],
    ]


def test_rowspan_in_middle_column():
    rows = [
        [Cell("a"), Cell("b", rowspan=2), Cell("c")],
        [Cell("d"), Cell("e")],
    ]
    assert expand_spans(rows) == [["a", "b", "c"], ["d", "b", "e"]]


def test_ragged_table_fails():
    with pytest.raises(SpanError):
        expand_spans([[Cell("a"), Cell("b")], [Cell("c")]])


def test_rowspan_past_last_row_fails():
    # 마지막 행이 rowspan으로 비어 있는 칸을 남기면 원표가 깨진 것이다
    with pytest.raises(SpanError):
        expand_spans([[Cell("a", rowspan=2), Cell("b")]])
