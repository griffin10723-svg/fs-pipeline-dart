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


SECRET = "dummy-test-value"


def test_redact_hides_key_in_url_and_message():
    msg = f"Max retries exceeded with url: /api/list.json?crtfc_key={SECRET}&corp_code=00126380 (Caused by ...)"
    out = dart.redact(msg)
    assert SECRET not in out
    assert "crtfc_key=***&corp_code=00126380" in out


@pytest.mark.parametrize("make_error", [
    lambda url: dart.requests.ConnectionError(f"Max retries exceeded with url: {url}"),
    lambda url: dart.requests.HTTPError(f"500 Server Error for url: {url}"),
])
def test_request_error_does_not_leak_key(monkeypatch, make_error):
    monkeypatch.setenv("DART_API_KEY", SECRET)
    monkeypatch.setattr(dart, "load_dotenv", lambda *a, **k: None)

    def fake_get(url, params, timeout):
        raise make_error(f"{url}?crtfc_key={params['crtfc_key']}")

    monkeypatch.setattr(dart.requests, "get", fake_get)
    with pytest.raises(dart.DartRequestError) as ei:
        dart.fetch_fs("00126380", 2024)
    assert SECRET not in str(ei.value)
    # 원래 예외(키 포함)가 traceback에 연결되지 않는다
    assert ei.value.__cause__ is None and ei.value.__suppress_context__


def test_fetch_fs_requests_consolidated_annual(monkeypatch):
    # 회계판단: D-001 응답에는 연결/별도 구분 칸이 없어서 요청 인자로만 연결이 정해진다
    sent = {}

    class _Resp:
        def json(self):
            return {"status": "000", "list": []}

    def fake_get(endpoint, params):
        sent.update(endpoint=endpoint, **params)
        return _Resp()

    monkeypatch.setattr(dart, "_get", fake_get)
    dart.fetch_fs("00126380", 2024)
    assert sent["endpoint"] == "fnlttSinglAcntAll.json"
    assert sent["fs_div"] == "CFS"
    assert sent["reprt_code"] == dart.ANNUAL == "11011"
