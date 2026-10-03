"""로더 경계의 데이터 불변식. 위반이 있으면 ERROR 로그와 예외로 멈춘다."""

import logging
from math import gcd

import pandas as pd

from fs_pipeline_dart.dart import ANNUAL, KEY_COLS

log = logging.getLogger(__name__)

SJ_DIVS = {"BS", "IS", "CIS", "CF", "SCE"}
NO_ID = "-표준계정코드 미사용-"
SEMANTIC_KEY = ["corp_code", "fiscal_year", "sj_div", "account_id"]
# 회계판단: 자산총계 = 부채총계 + 자본총계 (자본총계는 비지배지분 포함, ifrs-full_Equity)
ASSETS, LIABILITIES, EQUITY = "ifrs-full_Assets", "ifrs-full_Liabilities", "ifrs-full_Equity"
MAX_UNIT = 10**6  # 공시 표시 단위는 백만원이 가장 크다


class InvariantError(Exception):
    """데이터 불변식 위반. 메시지에 위반 전부를 담는다."""


def display_unit(amounts: pd.Series) -> int:
    """BS 금액들의 최대공약수로 표시 단위(원·천원·백만원)를 추정한다."""
    g = 0
    for a in amounts.dropna().astype("int64"):
        g = gcd(g, abs(int(a)))
    # 우연히 큰 공약수가 나와도 백만원을 넘기지 않는다. 0이면 1원으로 본다
    return min(g, MAX_UNIT) or 1


def _identity_errors(bs: pd.DataFrame) -> list[str]:
    errs = []
    for (corp, year), g in bs.groupby(["corp_code", "fiscal_year"]):
        vals = {}
        for name in (ASSETS, LIABILITIES, EQUITY):
            rows = g.loc[g["account_id"] == name, "amount"].dropna()
            if len(rows) != 1:
                errs.append(f"{corp} {year}: {name} 행이 {len(rows)}개 (1개여야 한다)")
            else:
                vals[name] = int(rows.iloc[0])
        if len(vals) < 3:
            continue
        unit = display_unit(g["amount"])
        gap = vals[ASSETS] - vals[LIABILITIES] - vals[EQUITY]
        if abs(gap) > unit:  # 표시 단위 ±1까지는 반올림 차이로 본다
            errs.append(f"{corp} {year}: 자산 - 부채 - 자본 = {gap:,}원 (허용 ±{unit:,}원)")
    return errs


def check(df: pd.DataFrame) -> list[str]:
    """위반 목록을 돌려준다. 비어 있으면 통과."""
    errs = []
    dup = int(df.duplicated(KEY_COLS).sum())  # 회계판단: D-011 유일성 키
    if dup:
        errs.append(f"유일성 키 중복 {dup}행")

    # 표준 ID가 있는 행은 SCE 외에 의미 키가 유일해야 조인에 쓸 수 있다 (D-011 정정)
    joinable = df[(df["sj_div"] != "SCE") & (df["account_id"] != NO_ID)]
    sem = int(joinable.duplicated(SEMANTIC_KEY).sum())
    if sem:
        errs.append(f"표준 ID 행의 의미 키 중복 {sem}행 (SCE 제외)")

    bad_sj = set(df["sj_div"]) - SJ_DIVS
    if bad_sj:
        errs.append(f"알 수 없는 sj_div {sorted(bad_sj)}")
    if (df["reprt_code"] != ANNUAL).any():
        errs.append("사업보고서(11011)가 아닌 행이 있다")

    # 회계판단: D-004 기업×연도마다 접수번호는 최종 정정본 하나
    if df["rcept_no"].isna().any() or (df["rcept_no"].str.strip() == "").any():
        errs.append("rcept_no가 빈 행이 있다")
    n = df.groupby(["corp_code", "fiscal_year"])["rcept_no"].nunique()
    for (corp, year), k in n[n != 1].items():
        errs.append(f"{corp} {year}: 접수번호가 {k}개 섞였다")

    errs += _identity_errors(df[df["sj_div"] == "BS"])
    return errs


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """통과하면 df를 그대로 돌려준다. 위반이 있으면 ERROR 로그 후 InvariantError."""
    errs = check(df)
    if errs:
        for e in errs:
            log.error("불변식 위반: %s", e)
        raise InvariantError(f"{len(errs)}건 위반: " + " | ".join(errs[:5]))
    log.info("불변식 통과 행=%d", len(df))
    return df
