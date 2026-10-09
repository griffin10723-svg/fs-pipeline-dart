"""Stage 1 게이트: 표본(기업×연도) 추출과 원문 대조 판정. DART 호출 없이 parquet만 읽는다."""

import argparse
import logging
from pathlib import Path

import pandas as pd

from fs_pipeline_dart.collect import OUT

log = logging.getLogger(__name__)

# 회계판단: D-003 계정은 표준계정ID로 고른다. 금융지주 영업이익은 D-010
ITEMS = {
    "매출액": ["ifrs-full_Revenue"],
    "영업이익": ["dart_OperatingIncomeLoss", "ifrs-full_ProfitLossFromOperatingActivities"],
    "자산총계": ["ifrs-full_Assets"],
    "순이자이익": ["ifrs-full_InterestRevenueExpense"],
}
SJ_BY_ITEM = {"매출액": ("IS", "CIS"), "영업이익": ("IS", "CIS"), "자산총계": ("BS",), "순이자이익": ("IS", "CIS")}
GATE_ITEMS = ["매출액", "영업이익", "자산총계"]

# 회계판단: D-015 업종 규칙 표. 여기 있는 기업만 매출액 대신 업종 대체 항목을 대조한다.
# 표에 없는 기업에서 계정이 비면 판정 보류(불통과)다
FORM = {"00688996": "금융지주"}
SUBSTITUTE = {"금융지주": {"매출액": "순이자이익"}}

OPEX = "dart_TotalSellingGeneralAdministrativeExpenses"  # 영업수익 형식의 영업비용
COST_OF_SALES = "ifrs-full_CostOfSales"
PICK_COLS = ["corp_code", "fiscal_year", "boundary"]


def draw(pool: pd.DataFrame, n: int, seed: int, boundary: list[tuple[str, int]] = ()) -> pd.DataFrame:
    """풀(corp_code·fiscal_year)에서 무작위 n건, 경계 사례는 그 밖에 따로 붙인다."""
    pool = pool[["corp_code", "fiscal_year"]].drop_duplicates()
    b = pd.DataFrame(list(boundary), columns=["corp_code", "fiscal_year"]).astype(pool.dtypes.to_dict())
    # 같은 경계 사례를 두 번 넣으면 여기서 멈춘다(one_to_one)
    missing = b.merge(pool, how="left", indicator=True, validate="one_to_one").query("_merge == 'left_only'")
    if len(missing):
        raise ValueError(f"경계 사례가 풀에 없다: {missing[['corp_code', 'fiscal_year']].values.tolist()}")

    # 경계 사례는 무작위 n건과 겹치지 않게 풀에서 뺀 뒤 뽑는다
    rest = pool.merge(b, how="left", indicator=True, validate="one_to_one").query("_merge == 'left_only'").drop(
        columns="_merge")
    log.info("표본 풀 %d건 - 경계 사례 %d건 = 무작위 추출 대상 %d건", len(pool), len(b), len(rest))
    if n > len(rest):
        raise ValueError(f"풀 {len(rest)}건(경계 사례 제외)에서 {n}건을 뽑을 수 없다")
    # 풀 순서가 parquet 행 순서에 따라 바뀌어도 같은 시드면 같은 표본이 나오게 정렬한다
    rest = rest.sort_values(["corp_code", "fiscal_year"], ignore_index=True)
    picked = rest.sample(n=n, random_state=seed).assign(boundary=False)
    out = pd.concat([picked, b.assign(boundary=True)], ignore_index=True)
    assert len(out) == n + len(b)
    return out[PICK_COLS]


def _value(g: pd.DataFrame, key: tuple, item: str) -> tuple[str | None, object]:
    """한 기업×연도에서 항목 값 하나. 없으면 (None, NA), 모호하면 예외."""
    for aid in ITEMS[item]:
        rows = g[(g["account_id"] == aid) & g["sj_div"].isin(SJ_BY_ITEM[item])]
        vals = rows["amount"].dropna().unique()
        if len(vals) > 1:
            # D-003: 같은 ID가 IS와 CIS에 모두 있으면 값이 같을 때만 허용
            raise ValueError(f"{key} {item} {aid}: 값이 {len(vals)}개 {list(vals)}")
        if len(vals) == 1:
            return aid, int(vals[0])
    if item == "매출액":
        return _revenue_by_identity(g, key)
    return None, pd.NA


def _revenue_by_identity(g: pd.DataFrame, key: tuple) -> tuple[str | None, object]:
    """`ifrs-full_Revenue`가 없을 때 손익 표 첫 줄을 매출로 본다. 첫 줄 − 영업비용 = 영업이익이 원 단위까지 맞을 때만.

    회계판단: D-005 영업수익 형식(매출원가 없음) 회사가 2021~2022에 영업수익을 다른 ID로 태깅했다
    (카카오 `ifrs-full_GrossProfit`, 크래프톤 `-표준계정코드 미사용-`). 진짜 매출총이익 − 판관비도 영업이익과
    같으므로 산식만으로는 못 가른다. 매출원가 줄이 있는 표(매출총이익 형식)는 대상에서 뺀다.
    """
    found = set()
    for sj in ("IS", "CIS"):
        t = g[g["sj_div"] == sj]
        if (t["account_id"] == COST_OF_SALES).any():
            continue
        opex = t.loc[t["account_id"] == OPEX, "amount"].dropna().unique()
        op = t.loc[t["account_id"].isin(ITEMS["영업이익"]), "amount"].dropna().unique()
        if len(opex) != 1 or len(op) != 1:
            continue
        first = t[t["ord"] == t["ord"].min()]
        if len(first) == 1 and pd.notna(rev := first["amount"].iloc[0]) and rev - opex[0] == op[0]:
            found.add((first["account_id"].iloc[0], int(rev)))
    if len({v for _, v in found}) > 1:
        raise ValueError(f"{key} 매출액 산식 후보가 둘 이상 {sorted(found)}")
    return next(iter(found)) if found else (None, pd.NA)


def items_for(corp_code: str) -> list[str]:
    """게이트 3개 항목. 업종 규칙 표에 있는 기업은 대체 항목으로 바꾼다 (D-015)."""
    sub = SUBSTITUTE.get(FORM.get(corp_code), {})
    return [sub.get(i, i) for i in GATE_ITEMS]


def extract(df: pd.DataFrame, picks: pd.DataFrame) -> pd.DataFrame:
    """표본마다 3개 항목(D-015 대체 포함)의 API 값과 접수번호. 계정이 없으면 금액을 비워 둔다(판정 보류)."""
    # 한 기업×연도에 행은 여럿, 표본 표는 기업×연도당 1행이다(many_to_one)
    sub = df.merge(picks[["corp_code", "fiscal_year"]], on=["corp_code", "fiscal_year"], how="inner",
                   validate="many_to_one")
    log.info("표본 행 추출: 전체 %d행 → 표본 %d건의 %d행", len(df), len(picks), len(sub))
    rows = []
    for key, g in sub.groupby(["corp_code", "fiscal_year"]):
        rcept = g["rcept_no"].unique()
        assert len(rcept) == 1  # 회계판단: D-004 validate()가 이미 보장한다
        for item in items_for(key[0]):
            aid, amt = _value(g, key, item)
            rows.append({
                "corp_code": key[0], "fiscal_year": key[1], "item": item,
                "account_id": aid, "api_amount": amt, "rcept_no": rcept[0],
            })
    cols = ["corp_code", "fiscal_year", "item", "account_id", "api_amount", "rcept_no"]
    out = pd.DataFrame(rows, columns=cols).astype({"api_amount": "Int64"})
    # 항목 행(여럿)에 표본(기업×연도당 1행)을 붙인다. right 조인이라 표본 순서가 유지된다
    out = out.merge(picks, on=["corp_code", "fiscal_year"], how="right", validate="many_to_one")[
        PICK_COLS + cols[2:]]
    log.info("표본 %d건 × 항목 %d개 → %d행", len(picks), len(GATE_ITEMS), len(out))
    absent = out["item"].isna()
    if absent.any():
        raise ValueError(f"parquet에 없는 표본: {out.loc[absent, ['corp_code', 'fiscal_year']].values.tolist()}")
    assert len(out) == len(picks) * len(GATE_ITEMS)
    return out


def judge(filled: pd.DataFrame) -> pd.DataFrame:
    """원문 값(source_amount, 표시 단위)과 단위 배수(unit)를 채운 표에 판정을 붙인다.

    일치: API 값 = 원문 값 × 단위. 어느 한쪽이 비면 판정 보류(NA)이고, 보류는 통과가 아니다.
    """
    src = pd.to_numeric(filled["source_amount"], errors="raise").astype("Int64")
    unit = pd.to_numeric(filled["unit"], errors="raise").astype("Int64")
    return filled.assign(match=filled["api_amount"] == src * unit)


def summary(judged: pd.DataFrame) -> dict:
    """게이트 판정: 표본(기업×연도)마다 3개 항목이 모두 일치해야 그 표본이 통과한다."""
    per = judged.groupby(["corp_code", "fiscal_year"])["match"].agg(lambda m: bool(m.notna().all() and m.all()))
    return {"samples": len(per), "passed": int(per.sum()), "pending": int(judged["match"].isna().sum()),
            "mismatch": int((judged["match"] == False).sum())}  # noqa: E712 — NA를 거르려고 == 를 쓴다


def to_markdown(t: pd.DataFrame, names: dict[str, str]) -> str:
    """docs/validation.md 20건 표 형식. 원천 값은 원문에서 사람이 채운다."""
    lines = []
    for i, (key, g) in enumerate(t.groupby(["corp_code", "fiscal_year"], sort=False), 1):
        for _, r in g.iterrows():
            api = "" if pd.isna(r["api_amount"]) else f"{int(r['api_amount']):,}"
            mark = " (경계)" if r["boundary"] else ""
            url = f"[{r['rcept_no']}](https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']})"
            lines.append(f"| {i}{mark} | {names.get(key[0], key[0])} | {key[1]} | {r['item']} |  | {api} |  | {url} |")
    return "\n".join(lines)


def _boundary(s: str) -> tuple[str, int]:
    corp, _, year = s.partition(":")
    return corp, int(year)


def main() -> None:
    from fs_pipeline_dart.dart import CORPS

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, required=True, help="validation.md에 기록할 추출 시드")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--boundary", action="append", default=[], type=_boundary, help="corp_code:연도, 여러 번")
    ap.add_argument("--out", type=Path, default=Path("outputs/sample.csv"))
    a = ap.parse_args()

    df = pd.read_parquet(OUT)
    picks = draw(df, a.n, a.seed, a.boundary)
    t = extract(df, picks)
    a.out.parent.mkdir(exist_ok=True)
    # 원문 값을 채울 빈 열. 다 채운 뒤 judge()로 판정한다
    t.assign(source_amount=pd.NA, unit=1_000_000).to_csv(a.out, index=False, encoding="utf-8-sig")
    print(f"풀 {len(df[['corp_code', 'fiscal_year']].drop_duplicates())}건, 시드 {a.seed}, 표본 {len(picks)}건 -> {a.out}")
    print(to_markdown(t, CORPS))


if __name__ == "__main__":
    main()
