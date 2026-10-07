"""표의 단위 표기와 금액 셀을 해석한다. 모르는 표기는 추측하지 않고 예외로 멈춘다."""

import re

# 원 단위 배수. KB금융 2022 원문에서 본 표기(억원·십억원·백만원·원·조원 등)와 천원을 받는다
MULTIPLIERS = {
    "원": 1,
    "천원": 10**3,
    "만원": 10**4,
    "백만원": 10**6,
    "천만원": 10**7,
    "억원": 10**8,
    "십억원": 10**9,
    "백억원": 10**10,
    "천억원": 10**11,
    "조원": 10**12,
}

_UNIT = re.compile(r"단\s*위\s*[:：]?\s*([^,，)\]）]+)")
_AMOUNT = re.compile(r"\d{1,3}(,\d{3})*|\d+")


class UnitError(ValueError):
    """단위 표기를 해석할 수 없다."""


class AmountError(ValueError):
    """금액 셀을 해석할 수 없다."""


def parse_unit(text: str) -> int:
    """'(단위 : 백만원)' 같은 표기에서 원 단위 배수를 돌려준다.

    '(단위: 백만원, %)'처럼 쉼표 뒤 보조 단위는 무시한다. 외화·주식 수 등 원화 금액이 아니면 예외.
    """
    m = _UNIT.search(text)
    if not m:
        raise UnitError(f"단위 표기가 없다: {text!r}")
    unit = re.sub(r"\s+", "", m.group(1))
    if unit not in MULTIPLIERS:
        raise UnitError(f"모르는 단위: {unit!r} ({text!r})")
    return MULTIPLIERS[unit]


def parse_amount(cell: str):
    """표시 단위 그대로의 금액 셀을 정수로. 빈 칸·'-'는 None.

    음수 표기: '(1,234)' · '△1,234' · '▲1,234' · '-1,234'. 소수·각주 기호 등은 예외.
    """
    s = cell.strip().replace(" ", "").replace(" ", "")
    if s in ("", "-", "–", "—"):
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    elif s[0] in "△▲-":
        neg, s = True, s[1:]
    if not _AMOUNT.fullmatch(s):
        raise AmountError(f"금액 변환 불가: {cell!r}")
    v = int(s.replace(",", ""))
    return -v if neg else v


def to_won(cell: str, multiplier: int):
    """금액 셀 × 단위 배수 = 원 단위 정수. 빈 칸은 None."""
    v = parse_amount(cell)
    return None if v is None else v * multiplier
