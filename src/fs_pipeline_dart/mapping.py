"""원문 계정명 → XBRL account_id 사전과 XBRL 대조 (D-014 3단계).

짝짓기: 같은 공시의 원문 행과 XBRL 행을 금액(표시 단위 ±1)으로 짝짓는다.
- 원문에서 같은 금액 행이 둘 이상이거나, 같은 금액의 XBRL ID가 둘 이상이면 자동으로 짝짓지 않는다(수작업 후보).
- 사전은 회사별, 키는 정규화한 계정명(statement.norm). 비슷한 이름 자동 허용은 하지 않는다.

대조(L2): 사전을 만든 공시로 다시 대조하면 정의상 전부 맞는다. 그래서 한 해를 빼고 나머지 해로 만든 사전을
뺀 해에 적용해 XBRL과 비교한다(leave-one-year-out).
"""

import argparse
import logging
from pathlib import Path

import pandas as pd

from fs_pipeline_dart import dart
from fs_pipeline_dart.collect import OUT
from fs_pipeline_dart.document import fetch_document
from fs_pipeline_dart.statement import norm, read_bs
from fs_pipeline_dart.validate import ASSETS, EQUITY, LIABILITIES, NO_ID, display_unit

log = logging.getLogger(__name__)

CORE = {"자산총계": ASSETS, "부채총계": LIABILITIES, "자본총계": EQUITY}
REPORT_DIR = Path("outputs/mapping")


def pair(doc: pd.DataFrame, xbrl: pd.DataFrame) -> pd.DataFrame:
    """한 공시의 원문 행마다 짝 상태. status: auto · dup_doc · dup_xbrl · none · no_amount."""
    tol = display_unit(doc["amount"])
    x = xbrl[(xbrl["account_id"] != NO_ID) & xbrl["amount"].notna()]
    amounts = doc["amount"].dropna().astype("int64")
    out = []
    for r in doc.itertuples(index=False):
        rec = {"corp_code": r.corp_code, "fiscal_year": r.fiscal_year, "ord": r.ord, "account_nm": r.account_nm,
               "name": norm(r.account_nm), "amount": r.amount, "account_id": None, "candidates": ""}
        if pd.isna(r.amount):
            out.append(rec | {"status": "no_amount"})
            continue
        a = int(r.amount)
        hit = x[(x["amount"].astype("int64") - a).abs() <= tol]
        ids = sorted(set(hit["account_id"]))
        rec["candidates"] = ";".join(ids)
        if ((amounts - a).abs() <= tol).sum() > 1:
            status = "dup_doc"
        elif len(ids) > 1:
            status = "dup_xbrl"
        elif len(ids) == 1:
            status, rec["account_id"] = "auto", ids[0]
        else:
            status = "none"
        out.append(rec | {"status": status})
    return pd.DataFrame(out)


def build_dictionary(pairs: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """자동 짝에서 회사별 사전(corp_code·name·account_id·years)과 충돌(같은 이름이 다른 ID)."""
    auto = pairs[pairs["status"] == "auto"]
    g = auto.groupby(["corp_code", "name"])["account_id"].agg(lambda s: sorted(set(s)))
    conflicts = g[g.map(len) > 1]
    years = auto.groupby(["corp_code", "name"])["fiscal_year"].agg(lambda s: ",".join(map(str, sorted(set(s)))))
    ok = g[g.map(len) == 1].map(lambda v: v[0])
    d = pd.DataFrame({"account_id": ok, "years": years.reindex(ok.index)}).reset_index()
    c = conflicts.map(";".join).rename("account_ids").reset_index()
    return d, c


def apply(doc: pd.DataFrame, dictionary: pd.DataFrame) -> pd.DataFrame:
    """사전에 있는 이름만 ID를 붙이고 나머지는 NO_ID. 한 공시에서 같은 ID가 두 행에 붙으면 예외."""
    m = dictionary.set_index(["corp_code", "name"])["account_id"]
    keys = list(zip(doc["corp_code"], doc["account_nm"].map(norm)))
    ids = [m.get(k, NO_ID) for k in keys]
    out = doc.assign(account_id=ids)
    used = out[out["account_id"] != NO_ID]
    dup = used[used.duplicated(["corp_code", "fiscal_year", "account_id"], keep=False)]
    if len(dup):
        raise ValueError(f"한 공시에서 같은 ID가 여러 행: {dup[['fiscal_year', 'account_nm', 'account_id']].values.tolist()}")
    return out


def compare(mapped: pd.DataFrame, xbrl: pd.DataFrame) -> pd.DataFrame:
    """ID가 붙은 원문 행을 같은 공시 XBRL과 비교. result: match · mismatch · missing_in_xbrl."""
    tol = display_unit(mapped["amount"])
    x = xbrl[xbrl["account_id"] != NO_ID].set_index("account_id")["amount"]
    rows = []
    for r in mapped[mapped["account_id"] != NO_ID].itertuples(index=False):
        if r.account_id not in x.index:
            res, xv = "missing_in_xbrl", None
        else:
            xv = x[r.account_id]
            same = pd.notna(r.amount) and pd.notna(xv) and abs(int(r.amount) - int(xv)) <= tol
            both_na = pd.isna(r.amount) and pd.isna(xv)
            res = "match" if same or both_na else "mismatch"
        rows.append({"corp_code": r.corp_code, "fiscal_year": r.fiscal_year, "account_nm": r.account_nm,
                     "account_id": r.account_id, "doc": r.amount, "xbrl": xv, "result": res})
    return pd.DataFrame(rows, columns=["corp_code", "fiscal_year", "account_nm", "account_id", "doc", "xbrl", "result"])


def core_missing(mapped: pd.DataFrame) -> list[str]:
    """핵심 계정(자산·부채·자본총계)이 ID를 못 받은 공시. D-014: 비면 예외 대상."""
    errs = []
    for (c, y), g in mapped.groupby(["corp_code", "fiscal_year"]):
        for name, aid in CORE.items():
            if aid not in set(g["account_id"]):
                errs.append(f"{c} {y} {name}")
    return errs


def holdout(docs: pd.DataFrame, pairs: pd.DataFrame, xbrl: pd.DataFrame) -> pd.DataFrame:
    """회사마다 한 해씩 빼고 나머지 해 사전으로 그 해를 대조한다."""
    results = []
    for (c, y), doc in docs.groupby(["corp_code", "fiscal_year"]):
        train = pairs[(pairs["corp_code"] == c) & (pairs["fiscal_year"] != y)]
        d, _ = build_dictionary(train)
        mapped = apply(doc, d)
        cmp = compare(mapped, xbrl[(xbrl["corp_code"] == c) & (xbrl["fiscal_year"] == y)])
        results.append({
            "corp_code": c, "fiscal_year": y, "rows_with_amount": int(doc["amount"].notna().sum()),
            "mapped": int((mapped["account_id"] != NO_ID).sum()),
            "match": int((cmp["result"] == "match").sum()),
            "mismatch": int((cmp["result"] != "match").sum()),
            "core_missing": ",".join(core_missing(mapped)),
        })
    return pd.DataFrame(results)


def run(corps: list[str], years: list[int]) -> dict[str, pd.DataFrame]:
    fs = pd.read_parquet(OUT)
    xbrl = fs[fs["sj_div"] == "BS"]
    docs, pairs = [], []
    for c in corps:
        for y in years:
            x = xbrl[(xbrl["corp_code"] == c) & (xbrl["fiscal_year"] == y)]
            if x.empty:
                log.warning("XBRL 없음, 건너뜀 %s %s", c, y)
                continue
            rcept, data = fetch_document(c, y)
            doc = read_bs(data, c, y, rcept)
            if rcept != x["rcept_no"].iloc[0]:
                log.warning("%s %s 원문 판 %s != XBRL 판 %s", c, y, rcept, x["rcept_no"].iloc[0])
            docs.append(doc)
            pairs.append(pair(doc, x))
    docs, pairs = pd.concat(docs, ignore_index=True), pd.concat(pairs, ignore_index=True)
    dictionary, conflicts = build_dictionary(pairs)
    return {"docs": docs, "pairs": pairs, "dictionary": dictionary, "conflicts": conflicts,
            "holdout": holdout(docs, pairs, xbrl)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corps", type=int, default=5)
    ap.add_argument("--years", default="2023-2025")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    lo, _, hi = a.years.partition("-")
    out = run(list(dart.CORPS)[: a.corps], list(range(int(lo), int(hi or lo) + 1)))
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in out.items():
        df.to_csv(REPORT_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")
    h = out["holdout"]
    log.info("대조(한 해 빼기) 불일치 %d건, 핵심 계정 누락 %d공시, 사전 %d개, 충돌 %d개",
             h["mismatch"].sum(), (h["core_missing"] != "").sum(), len(out["dictionary"]), len(out["conflicts"]))
    log.info("짝 상태 %s", out["pairs"]["status"].value_counts().to_dict())


if __name__ == "__main__":
    main()
