"""dart.py 단위 테스트. 네트워크 없이 돈다."""

import pandas as pd
import pytest

from fs_pipeline_dart import dart


def test_to_amount_parses_won_integer_with_sign():
    assert dart.to_amount("514531948000000") == 514_531_948_000_000
    assert dart.to_amount("-1,234") == -1234  # 영업손실 부호가 살아 있어야 한다


@pytest.mark.parametrize("blank", ["", " ", "-"])
def test_to_amount_blank_is_na(blank):
    assert dart.to_amount(blank) is pd.NA


def test_to_amount_rejects_non_numeric():
    with pytest.raises(ValueError):
        dart.to_amount("1.5조")


def test_check_rcept_matches_and_mismatches():
    rows = [{"rcept_no": "20250311001085"}, {"rcept_no": "20250311001085"}]
    assert dart.check_rcept(rows, "20250311001085") == "20250311001085"
    with pytest.raises(dart.RceptMismatch):
        dart.check_rcept(rows, "20250401000001")  # 정정본이 더 있는 경우
    with pytest.raises(dart.RceptMismatch):
        dart.check_rcept(rows + [{"rcept_no": "20240101000001"}], "20250311001085")


def _row(**kw):
    base = {
        "corp_code": "00126380", "bsns_year": "2024", "sj_div": "SCE",
        "account_id": "dart_EquityAtBeginningOfPeriod", "ord": "4", "account_nm": "기초자본",
        "account_detail": "자본금", "thstrm_amount": "100", "currency": "KRW",
        "rcept_no": "20250311001085", "reprt_code": "11011",
    }
    return base | kw


def test_to_frame_keeps_every_row_and_key_is_unique_with_detail():
    # SCE: 같은 ord에 구성요소 열이 여럿이다. account_detail이 키에 있어야 유일하다
    rows = [_row(), _row(account_detail="이익잉여금", thstrm_amount="200")]
    df = dart.to_frame(rows)
    assert len(df) == 2  # 계정을 거르지 않는다 (D-003)
    assert not df.duplicated(dart.KEY_COLS).any()
    assert df["amount"].dtype == "Int64"


def test_to_frame_blank_amount_becomes_na_not_zero():
    df = dart.to_frame([_row(thstrm_amount="")])
    assert df["amount"].isna().all()
