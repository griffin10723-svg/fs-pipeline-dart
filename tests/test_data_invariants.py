"""validate()가 결정 기록(D-001·D-003·D-004·D-011)을 실제로 강제하는지 본다."""

from pathlib import Path

import pandas as pd
import pytest

from fs_pipeline_dart import validate as v


def _bs(assets, liab, equity):
    """한 기업×연도의 BS 3행. 금액은 백만원 단위로 반올림된 값을 쓴다."""
    base = {
        "corp_code": "X", "fiscal_year": 2024, "sj_div": "BS", "ord": 1,
        "account_nm": "", "account_detail": "-", "currency": "KRW",
        "rcept_no": "20250311000001", "reprt_code": "11011",
    }
    rows = [
        base | {"account_id": v.ASSETS, "amount": assets, "ord": 1},
        base | {"account_id": v.LIABILITIES, "amount": liab, "ord": 2},
        base | {"account_id": v.EQUITY, "amount": equity, "ord": 3},
    ]
    return pd.DataFrame(rows).astype({"amount": "Int64"})


M = 1_000_000  # 백만원


def test_clean_data_passes():
    assert v.check(_bs(100 * M, 60 * M, 40 * M)) == []


def test_identity_rounding_within_one_unit_passes():
    # 백만원 표시 재무제표의 반올림 차이: 1백만원까지는 정상
    assert v.check(_bs(100 * M, 60 * M, 39 * M)) == []


def test_identity_gap_above_one_unit_fails():
    errs = v.check(_bs(100 * M, 60 * M, 38 * M))
    assert any("자산 - 부채 - 자본" in e for e in errs)


def test_validate_raises_and_logs_error(caplog):
    with pytest.raises(v.InvariantError), caplog.at_level("ERROR"):
        v.validate(_bs(100 * M, 60 * M, 30 * M))
    assert "불변식 위반" in caplog.text


def test_duplicate_key_fails():
    df = _bs(100 * M, 60 * M, 40 * M)
    assert any("유일성 키" in e for e in v.check(pd.concat([df, df.iloc[[0]]])))


def test_two_rcept_nos_for_one_company_year_fail():
    # D-004: 기업×연도에 접수번호가 둘이면 최종 정정본 하나로 못 가른 것이다
    df = _bs(100 * M, 60 * M, 40 * M)
    df.loc[0, "rcept_no"] = "20240101000001"
    assert any("접수번호가 2개" in e for e in v.check(df))


def test_missing_total_row_fails():
    df = _bs(100 * M, 60 * M, 40 * M)
    assert any(v.EQUITY in e for e in v.check(df[df["account_id"] != v.EQUITY]))


def test_standard_id_semantic_key_must_be_unique_outside_sce():
    df = _bs(100 * M, 60 * M, 40 * M)
    dup = df.iloc[[0]].assign(ord=99)  # ord만 다른 같은 표준 ID
    assert any("의미 키" in e for e in v.check(pd.concat([df, dup])))


def test_placeholder_id_rows_may_share_semantic_key():
    # 표준 ID가 없는 행은 의미 키가 겹쳐도 보존한다(D-003). 조인에서만 제외한다
    df = _bs(100 * M, 60 * M, 40 * M)
    extra = df.iloc[[0, 0]].assign(account_id=v.NO_ID, ord=[10, 11])
    assert v.check(pd.concat([df, extra])) == []


def test_display_unit_infers_million_and_won():
    assert v.display_unit(pd.Series([5 * M, 7 * M, 11 * M], dtype="Int64")) == M
    assert v.display_unit(pd.Series([5 * M + 1, 7 * M], dtype="Int64")) == 1


@pytest.mark.skipif(
    not Path("data/processed/fs_long.parquet").exists(),
    reason="수집 결과 없음: collect를 먼저 실행",
)
def test_collected_v0_data_passes():
    assert v.check(pd.read_parquet("data/processed/fs_long.parquet")) == []
