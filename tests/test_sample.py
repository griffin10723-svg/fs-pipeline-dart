"""표본 추출·대조 판정이 게이트 규칙(시드 재현·경계 사례 별도·보류는 통과 아님)을 지키는지 본다."""

import pandas as pd
import pytest

from fs_pipeline_dart import sample as s

M = 1_000_000


def _pool(corps=5, years=range(2021, 2026)):
    return pd.DataFrame(
        [{"corp_code": f"C{i}", "fiscal_year": y} for i in range(corps) for y in years]
    )


def _fs(corp, year, rows):
    base = {"corp_code": corp, "fiscal_year": year, "rcept_no": f"{year + 1}0301000001"}
    return pd.DataFrame([base | dict(zip(["sj_div", "account_id", "amount"], r)) for r in rows])


def _company(corp="C0", year=2024):
    return _fs(corp, year, [
        ("CIS", "ifrs-full_Revenue", 300 * M),
        ("CIS", "dart_OperatingIncomeLoss", 30 * M),
        ("BS", "ifrs-full_Assets", 500 * M),
    ]).astype({"amount": "Int64"})


def test_same_seed_same_sample_regardless_of_row_order():
    pool = _pool()
    a = s.draw(pool, 10, seed=7)
    b = s.draw(pool.sample(frac=1, random_state=1), 10, seed=7)
    pd.testing.assert_frame_equal(a, b)


def test_boundary_added_outside_random_draw():
    out = s.draw(_pool(), 20, seed=7, boundary=[("C1", 2023)])
    assert len(out) == 21
    assert out["boundary"].sum() == 1
    # 경계 사례가 무작위 쪽에 한 번 더 뽑히지 않는다
    assert not out[["corp_code", "fiscal_year"]].duplicated().any()


def test_pool_too_small_fails():
    # v0 15건(5사×3년)에서 20건은 못 뽑는다
    with pytest.raises(ValueError, match="뽑을 수 없다"):
        s.draw(_pool(years=range(2023, 2026)), 20, seed=7)


def test_boundary_not_in_pool_fails():
    with pytest.raises(ValueError, match="풀에 없다"):
        s.draw(_pool(), 5, seed=7, boundary=[("C9", 2024)])


def test_extract_picks_values_and_rcept():
    picks = pd.DataFrame([{"corp_code": "C0", "fiscal_year": 2024, "boundary": False}])
    t = s.extract(_company(), picks)
    assert list(t["item"]) == ["매출액", "영업이익", "자산총계"]
    assert list(t["api_amount"]) == [300 * M, 30 * M, 500 * M]
    assert set(t["rcept_no"]) == {"20250301000001"}


def test_financial_holding_operating_income_and_missing_revenue():
    # D-010: 금융지주는 매출액 줄이 없고 영업이익 ID가 다르다. 매출액은 비워 두고 판정 보류
    df = _fs("KB", 2024, [
        ("CIS", "ifrs-full_ProfitLossFromOperatingActivities", 7 * M),
        ("BS", "ifrs-full_Assets", 700 * M),
    ]).astype({"amount": "Int64"})
    picks = pd.DataFrame([{"corp_code": "KB", "fiscal_year": 2024, "boundary": True}])
    t = s.extract(df, picks).set_index("item")
    assert pd.isna(t.loc["매출액", "api_amount"])
    assert t.loc["영업이익", "account_id"] == "ifrs-full_ProfitLossFromOperatingActivities"


def test_is_and_cis_disagree_fails():
    # D-003: 같은 ID가 IS·CIS에 모두 있으면 값이 같을 때만 허용
    df = pd.concat([_company(), _fs("C0", 2024, [("IS", "ifrs-full_Revenue", 301 * M)])]).astype({"amount": "Int64"})
    picks = pd.DataFrame([{"corp_code": "C0", "fiscal_year": 2024, "boundary": False}])
    with pytest.raises(ValueError, match="값이 2개"):
        s.extract(df, picks)


def test_sample_missing_from_parquet_fails():
    picks = pd.DataFrame([{"corp_code": "C1", "fiscal_year": 2024, "boundary": False}])
    with pytest.raises(ValueError, match="parquet에 없는"):
        s.extract(_company(), picks)


def test_judge_unit_and_pending_is_not_pass():
    picks = pd.DataFrame([{"corp_code": "C0", "fiscal_year": 2024, "boundary": False}])
    t = s.extract(_company(), picks)
    t["unit"] = M
    t["source_amount"] = [300, 30, pd.NA]  # 자산총계는 아직 원문을 안 봤다
    r = s.summary(s.judge(t))
    assert r == {"samples": 1, "passed": 0, "pending": 1, "mismatch": 0}

    t["source_amount"] = [300, 30, 500]
    assert s.summary(s.judge(t))["passed"] == 1

    t["source_amount"] = [300, 31, 500]  # 단위 배수 뒤 1백만원 차이도 불일치다
    assert s.summary(s.judge(t))["mismatch"] == 1
