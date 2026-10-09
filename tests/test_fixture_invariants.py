"""커밋된 작은 표본(tests/fixtures)으로 돌리는 DART 불변식.

수집 결과(data/)는 gitignore라서 새로 clone하면 실데이터 테스트가 건너뛰어진다.
이 파일은 clone 직후에도 실제 공시 값으로 D-001·D-003·D-004·D-011 검사가 돌게 한다.
표본: 삼성전자 2024 · 카카오 2023(경계: 정정 3회, 원 단위) · KB금융 2024(경계: 1년 뒤 정정, 금융업).
"""

from pathlib import Path

import pandas as pd
import pytest

from fs_pipeline_dart import validate as v

FIXTURE = Path(__file__).parent / "fixtures" / "fs_long_sample.parquet"

# 기준값: docs/validation.md 22건 대조에서 사람이 공시뷰어 본 표로 읽은 자산총계(원 환산)
ASSETS_FROM_FILING = {
    ("00126380", 2024): (514_531_948_000_000, "20250311001085"),
    ("00258801", 2023): (25_179_968_939_321, "20240418000375"),
    ("00688996", 2024): (757_845_532_000_000, "20260324000822"),
}


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    return pd.read_parquet(FIXTURE)


def test_fixture_passes_all_invariants(df):
    assert v.check(df) == []


def test_fixture_covers_three_firm_years(df):
    assert set(zip(df["corp_code"], df["fiscal_year"], strict=True)) == set(ASSETS_FROM_FILING)


def test_consolidated_annual_report_only(df):
    # 회계판단: D-001 연결(CFS) 기준. 응답에 fs_div 칸이 없어 사업보고서(11011)만 들어왔는지로 확인한다
    assert set(df["reprt_code"]) == {"11011"}


def test_one_final_rcept_no_per_firm_year(df):
    # 회계판단: D-004 최종 정정본 1판. 한 기업×연도에 접수번호가 둘이면 판이 섞인 것이다
    assert (df.groupby(["corp_code", "fiscal_year"])["rcept_no"].nunique() == 1).all()


@pytest.mark.parametrize(("key", "expected"), ASSETS_FROM_FILING.items())
def test_assets_match_filing(df, key, expected):
    amount, rcept_no = expected
    g = df[(df["corp_code"] == key[0]) & (df["fiscal_year"] == key[1])]
    assets = g[(g["sj_div"] == "BS") & (g["account_id"] == v.ASSETS)]
    assert len(assets) == 1
    assert int(assets["amount"].iloc[0]) == amount
    assert assets["rcept_no"].iloc[0] == rcept_no
