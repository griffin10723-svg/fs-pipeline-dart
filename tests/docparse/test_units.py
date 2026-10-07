"""단위·금액 해석은 모르는 표기에서 추측하지 않고 멈춘다 (D-014 fail loud)."""

import pytest

from docparse.units import AmountError, UnitError, parse_amount, parse_unit, to_won


@pytest.mark.parametrize("text, mult", [
    ("(단위 : 백만원)", 10**6),
    ("(단위: 백만원)", 10**6),
    ("(단위:원)", 1),
    ("단위 : 천원", 10**3),
    ("(단위 : 억원)", 10**8),
    ("(단위 : 십억원)", 10**9),
    ("(단위 : 조원)", 10**12),
    ("(단위: 백만원, %)", 10**6),
    ("(단 위 : 백 만 원)", 10**6),
    ("[단위：백만원]", 10**6),
])
def test_parse_unit(text, mult):
    assert parse_unit(text) == mult


@pytest.mark.parametrize("text", ["(단위 : 천USD)", "(단위 : 주)", "(단위 : %)", "연결재무상태표"])
def test_unknown_or_missing_unit_fails(text):
    with pytest.raises(UnitError):
        parse_unit(text)


@pytest.mark.parametrize("cell, v", [
    ("701,170,848", 701170848),
    ("1234", 1234),
    ("(1,234)", -1234),
    ("△1,234", -1234),
    ("▲1,234", -1234),
    ("-1,234", -1234),
    (" 1,234 ", 1234),
    ("0", 0),
    ("", None),
    ("-", None),
])
def test_parse_amount(cell, v):
    assert parse_amount(cell) == v


@pytest.mark.parametrize("cell", ["1,23", "1.5", "12,345(주3)", "N/A", "1,234,"])
def test_bad_amount_fails(cell):
    with pytest.raises(AmountError):
        parse_amount(cell)


def test_to_won_kb_2022_assets():
    # KB금융 2022 연결 자산총계 (백만원) — 실측 기준값
    assert to_won("701,170,848", parse_unit("(단위 : 백만원)")) == 701_170_848_000_000
