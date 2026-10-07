"""원문 계정명 → XBRL account_id 사전, XBRL 대조, XBRL 없는 해로 잇기 (D-014 3·5단계, D-005 부분).

짝짓기: 같은 공시의 원문 행과 XBRL 행을 금액(표시 단위 ±1)으로 짝짓는다.
- 원문에서 같은 금액 행이 둘 이상이거나, 같은 금액의 XBRL ID가 둘 이상이면 자동으로 짝짓지 않는다(수작업 후보).
- 사전은 회사별, 키는 정규화한 계정명(statement.norm). 비슷한 이름 자동 허용은 하지 않는다.

ID 선택 (회계판단: D-005 부분, 작업자 2026-10-07):
- 회사가 같은 계정의 태그를 해마다 바꾼다. 최근 연도 ID를 쓴다. 다음 해 XBRL 전기 금액이 이번 해 당기 금액과 같으면
  옛 ID → 새 ID로 바꿔 읽는다(rename_map). 재작성으로 금액이 다르면 이어지지 않고 이름 사전이 남는다.
- XBRL 없는 해는 다음 해 보고서의 전기 열(그 해 ID가 붙은 값)과 금액으로 먼저 잇고, 안 되면 이름 사전으로 붙인다(bridge).

대조(L2): 사전을 만든 공시로 다시 대조하면 정의상 전부 맞는다. 그래서 한 해를 빼고 나머지 해로 만든 사전과
다음 해 전기 열로 그 해에 ID를 붙여 XBRL과 비교한다(holdout). XBRL 없는 해에 쓰는 방법과 같은 방법이다.
"""

import argparse
import json
import logging
import re
from pathlib import Path

import pandas as pd

from docparse import store
from docparse.model import Document
from fs_pipeline_dart import dart
from fs_pipeline_dart.collect import OUT, RAW
from fs_pipeline_dart.document import fetch_document
from fs_pipeline_dart.statement import (
    NET_INCOME,
    body_document,
    find_statement,
    norm,
    parse_statement,
)
from fs_pipeline_dart.validate import (
    ASSETS,
    EQUITY,
    LIABILITIES,
    NO_ID,
    display_unit,
    validate,
)

log = logging.getLogger(__name__)

CORE = {"자산총계": ASSETS, "부채총계": LIABILITIES, "자본총계": EQUITY}
PROFIT_LOSS = "ifrs-full_ProfitLoss"
SJ = {"BS": ("BS",), "IS": ("IS", "CIS"), "CF": ("CF",)}


# 금액이 자산총계와 같아 짝짓기로는 늘 모호한 합계 행. 핵심 계정 검사에는 넣지 않는다
FIXED_BS = CORE | {"부채와자본총계": "ifrs-full_EquityAndLiabilities", "자본과부채총계": "ifrs-full_EquityAndLiabilities"}
MANUAL = Path(__file__).with_name("manual_mapping.csv")

# 회계판단: D-006 기준서 전환. 사전을 만든 해가 시행 뒤이고 붙일 해가 시행 전이면, 이름이 같아도 범위가
# 다를 수 있어 자동으로 붙이지 않는다(KB 2022 보험비용: 1104호 16.44조 vs 같은 해 1117호 8.76조).
# 작업자가 manual_mapping.csv에서 승인하면 붙는다. (기준서, 시행 첫 사업연도, 해당 계정명 패턴)
TRANSITIONS = [
    ("1117호 보험계약", 2023, re.compile(r"보험")),
    ("1109호 금융상품", 2018, re.compile(r"금융자산|금융부채|금융상품|대출채권|대손|충당금|손상")),
    ("1116호 리스", 2019, re.compile(r"리스|사용권")),
]


def crossed_transition(name: str, from_year: int, to_year: int) -> str | None:
    """사전 해(from_year)에서 붙일 해(to_year)로 갈 때 넘는 기준서 전환. 없으면 None."""
    for std, first, pat in TRANSITIONS:
        if to_year < first <= from_year and pat.search(name):
            return std
    return None


def core_id(kind: str, name: str) -> str | None:
    """이름으로 고정하는 계정. BS는 자산·부채·자본총계(+부채와자본총계), IS는 당기순이익(손익) (D-014)."""
    if kind == "BS":
        return FIXED_BS.get(name)
    return PROFIT_LOSS if NET_INCOME.match(name) else None
REPORT_DIR = Path("outputs/mapping")
DOC_OUT = Path("data/processed/fs_document.parquet")
DOC_LAYER = Path("data/processed/document")  # 범용 층: 접수번호마다 문단·표·셀 parquet
DICT_VERSION = "bs-0.1"  # 회계판단: D-005 assumptions에 남길 계정 사전 규칙 버전


# ---------- XBRL 쪽 ----------

def xbrl_rows(corp_code: str, year: int, kind: str = "BS") -> pd.DataFrame | None:
    """원본 JSON의 표준 ID 행: account_id · thstrm · frmtrm (원). 받은 적 없으면 None.

    IS는 IS·CIS를 함께 본다. 같은 ID가 둘에 같은 금액으로 있으면 한 행으로 친다(D-003).
    """
    path = RAW / f"{corp_code}_{year}.json"
    if not path.exists():
        return None
    rows = [r for r in json.loads(path.read_text(encoding="utf-8"))["list"]
            if r["sj_div"] in SJ[kind] and r["account_id"] != NO_ID]
    out = pd.DataFrame({
        "account_id": [r["account_id"] for r in rows],
        "thstrm": pd.array([dart.to_amount(r.get("thstrm_amount") or "") for r in rows], dtype="Int64"),
        "frmtrm": pd.array([dart.to_amount(r.get("frmtrm_amount") or "") for r in rows], dtype="Int64"),
    })
    return out.drop_duplicates()


def _tol(doc: pd.DataFrame) -> int:
    """짝짓기 허용 오차 = 표시 단위. 주당이익 행(원 단위)을 넣으면 최대공약수가 1원으로 떨어져 뺀다."""
    return display_unit(doc.loc[~doc["account_nm"].str.contains("주당"), "amount"])


def _unique_amounts(s: pd.Series) -> pd.Series:
    s = s.dropna()
    return s[~s.duplicated(keep=False)]


def rename_map(corp_code: str, years: list[int], kind: str = "BS") -> dict[str, str]:
    """옛 ID → 최근 연도 ID. Y년 당기 금액과 Y+1년 전기 금액이 같고 Y+1년에 옛 ID가 사라졌을 때만."""
    step: dict[str, str] = {}
    for y in sorted(years)[:-1]:
        cur, nxt = xbrl_rows(corp_code, y, kind), xbrl_rows(corp_code, y + 1, kind)
        if cur is None or nxt is None:
            continue
        # IS·CIS에 같은 ID가 다른 금액으로 있으면 어느 쪽인지 모르므로 잇지 않는다
        cur = cur[~cur["account_id"].duplicated(keep=False)]
        nxt = nxt[~nxt["account_id"].duplicated(keep=False)]
        gone = cur[~cur["account_id"].isin(nxt["account_id"])]
        new = nxt[~nxt["account_id"].isin(cur["account_id"])]
        a_old = _unique_amounts(cur.set_index("account_id")["thstrm"])
        a_new = _unique_amounts(new.set_index("account_id")["frmtrm"])
        for old in gone["account_id"]:
            if old in a_old.index and (hit := a_new[a_new == a_old[old]]).size == 1:
                step[old] = hit.index[0]
    out = {}
    for old in step:  # 여러 해에 걸친 바뀜을 끝까지 따라간다
        new, seen = step[old], {old}
        while new in step and new not in seen:
            seen.add(new)
            new = step[new]
        out[old] = new
    return out


def _tr(ids: pd.Series, rmap: dict[str, str]) -> pd.Series:
    return ids.map(lambda i: rmap.get(i, i))


# ---------- 사전 ----------

def name_keys(doc: pd.DataFrame) -> pd.Series:
    """사전 키: 정규화한 계정명. 한 공시에 같은 이름이 또 나오면 '#2'·'#3'을 붙인다.

    재무상태표에는 유동·비유동 아래 같은 이름(예: 삼성전자 '충당부채')이 두 번 나온다. 이름만으로는 구분할 수 없어
    표 안 등장 순서로 가른다. 한 행이 빠지면 순번이 밀리므로 apply()가 개수를 함께 본다(작업자 승인 2026-10-07).
    """
    names = doc["account_nm"].map(norm)
    n = names.groupby([doc["corp_code"], doc["fiscal_year"], names]).cumcount() + 1
    return names.where(n == 1, names + "#" + n.astype(str))


def _name_counts(doc: pd.DataFrame) -> pd.Series:
    names = doc["account_nm"].map(norm)
    return names.groupby([doc["corp_code"], doc["fiscal_year"], names]).transform("size")


def _hits(x: pd.DataFrame, a: int, tol: int) -> tuple[list[str], bool]:
    """금액 a와 같은 XBRL ID들. 같은 부호로 없으면 반대 부호로 찾고 flip=True.

    원문은 비용을 음수로, XBRL은 양수로 적기도 한다(KB금융 일반관리비 −4.5조 ↔ 4.5조).
    """
    amt = x["amount"].astype("int64")
    ids = sorted(set(x.loc[(amt - a).abs() <= tol, "account_id"]))
    if ids or a == 0:
        return ids, False
    return sorted(set(x.loc[(amt + a).abs() <= tol, "account_id"])), True


def pair(doc: pd.DataFrame, xbrl: pd.DataFrame) -> pd.DataFrame:
    """한 공시의 원문 행마다 짝 상태. status: auto · dup_doc · dup_xbrl · none · no_amount. flip = 부호 반대."""
    tol = _tol(doc)
    x = xbrl[(xbrl["account_id"] != NO_ID) & xbrl["amount"].notna()]
    amounts = doc["amount"].dropna().astype("int64")
    out = []
    for r, key, cnt in zip(doc.itertuples(index=False), name_keys(doc), _name_counts(doc)):
        rec = {"corp_code": r.corp_code, "fiscal_year": r.fiscal_year, "ord": r.ord, "account_nm": r.account_nm,
               "name": key, "count": int(cnt), "amount": r.amount, "account_id": None, "flip": False,
               "candidates": ""}
        if pd.isna(r.amount):
            out.append(rec | {"status": "no_amount"})
            continue
        a = int(r.amount)
        ids, flip = _hits(x, a, tol)
        rec["candidates"] = ";".join(ids)
        if ((amounts.abs() - abs(a)).abs() <= tol).sum() > 1:
            status = "dup_doc"
        elif len(ids) > 1:
            status = "dup_xbrl"
        elif len(ids) == 1:
            status, rec["account_id"], rec["flip"] = "auto", ids[0], flip
        else:
            status = "none"
        out.append(rec | {"status": status})
    return pd.DataFrame(out)


def build_dictionary(pairs: pd.DataFrame, rmap: dict[str, str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """자동 짝에서 회사별 사전과 충돌 기록. 같은 이름의 ID가 해마다 다르면 최근 연도 ID를 쓴다 (D-005 부분).

    사전 칸: corp_code · name · account_id · flip · year(ID를 가져온 해) · count(그해 같은 이름 개수) · years.
    부호(flip)도 최근 연도를 따른다. 충돌 칸: 최근 연도 ID로 바꿔 읽은 뒤에도 해마다 ID가 다른 이름. 정보용이다.
    """
    cols = ["corp_code", "name", "account_id", "flip", "year", "count", "years"]
    auto = pairs[pairs["status"] == "auto"]
    if auto.empty:
        return pd.DataFrame(columns=cols), pd.DataFrame(columns=["corp_code", "name", "account_ids"])
    auto = auto.assign(account_id=_tr(auto["account_id"], rmap or {}))
    if "flip" not in auto:
        auto = auto.assign(flip=False)
    latest = auto.sort_values("fiscal_year").groupby(["corp_code", "name"]).tail(1)
    years = auto.groupby(["corp_code", "name"])["fiscal_year"].agg(lambda s: ",".join(map(str, sorted(set(s)))))
    d = latest.rename(columns={"fiscal_year": "year"})[["corp_code", "name", "account_id", "flip", "year", "count"]]
    d = d.merge(years.rename("years").reset_index(), on=["corp_code", "name"], how="left", validate="one_to_one")
    ids = auto.groupby(["corp_code", "name"])["account_id"].agg(lambda s: sorted(set(s)))
    c = ids[ids.map(len) > 1].map(";".join).rename("account_ids").reset_index()
    return d[cols].reset_index(drop=True), c


def manual_dictionary(path: Path = MANUAL) -> pd.DataFrame:
    """작업자가 결정한 수작업 매핑(status = approved·rejected). 제안(proposed)은 쓰지 않는다.

    회계판단: D-014 수작업 항목은 작업자 승인. 거절(rejected)은 기록만이 아니라 자동 사전도 막는다.
    """
    cols = ["corp_code", "kind", "name", "account_id", "flip", "status"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    m = pd.read_csv(path, dtype={"corp_code": str}, encoding="utf-8")
    return m[m["status"].isin(["approved", "rejected"])][cols].astype({"flip": bool})


def _assign(doc: pd.DataFrame, dictionary: pd.DataFrame, kind: str,
            manual: pd.DataFrame | None = None) -> pd.DataFrame:
    """ID·부호를 정한다(금액은 아직 원문 부호). method: core · manual · rejected · name · count_guard ·
    transition_guard · name_dup · none.

    순서: 이름 고정 계정 → 승인된 수작업 매핑 → 자동 사전.
    """
    m = dictionary.set_index(["corp_code", "name"])
    man = manual_dictionary() if manual is None else manual
    man = man[man["kind"] == kind].set_index(["corp_code", "name"])
    ids, methods, flips = [], [], []
    for c, y, key, cnt in zip(doc["corp_code"], doc["fiscal_year"], name_keys(doc), _name_counts(doc)):
        flip = False
        if aid := core_id(kind, key):
            method = "core"
        elif (c, key) in man.index:
            row = man.loc[(c, key)]
            if row["status"] == "rejected":  # 작업자가 거절한 매핑은 자동 사전·경계 장치와 상관없이 붙이지 않는다
                aid, method = NO_ID, "rejected"
            else:
                aid, method, flip = row["account_id"], "manual", bool(row["flip"])
        elif (c, key) in m.index:
            row = m.loc[(c, key)]
            if (cnt > 1 or row["count"] > 1) and cnt != row["count"]:
                log.warning("%s %s: 같은 이름 %d개(사전 %s년 %d개), ID를 붙이지 않는다", c, key, cnt, row["year"], row["count"])
                aid, method = NO_ID, "count_guard"
            elif std := crossed_transition(key, int(row["year"]), int(y)):
                log.warning("%s %s %s: %s 경계를 넘는 이름 매칭(%s) — 승인 전에는 붙이지 않는다",
                            c, y, key, std, row["account_id"])
                aid, method = NO_ID, "transition_guard"
            else:
                aid, method, flip = row["account_id"], "name", bool(row.get("flip", False))
        else:
            aid, method = NO_ID, "none"
        ids.append(aid)
        methods.append(method)
        flips.append(flip)
    out = doc.assign(account_id=ids, method=methods, flip=flips)
    # 해마다 이름 뜻이 바뀌면(카카오 '파생상품자산') 최근 연도 ID로 두 이름이 한 ID에 모인다. 어느 쪽도 믿지 않는다
    named = out["method"] == "name"
    dup = named & out.duplicated(["corp_code", "fiscal_year", "sj_div", "account_id"], keep=False) & (out["account_id"] != NO_ID)
    for r in out[dup].itertuples():
        log.warning("%s %s %s: 이름 사전 ID %s가 겹쳐 붙이지 않는다", r.corp_code, r.fiscal_year, r.account_nm, r.account_id)
    out.loc[dup, ["account_id", "method", "flip"]] = [NO_ID, "name_dup", False]
    return out


def _signed(out: pd.DataFrame) -> pd.DataFrame:
    """ID가 붙은 행의 금액을 XBRL 부호로 바꾼다. 회계판단: D-005 부분(최근 연도 규칙)."""
    _check_dup_ids(out)
    amt = out["amount"].where(~out["flip"].astype(bool), -out["amount"])
    return out.assign(amount=amt)


def apply(doc: pd.DataFrame, dictionary: pd.DataFrame, kind: str = "BS") -> pd.DataFrame:
    """이름 사전으로 ID를 붙이고 금액을 XBRL 부호로 바꾼다.

    - 핵심 계정은 이름으로 고정(자산총계는 '부채와자본총계'와 금액이 같아 짝짓기로는 늘 모호하다).
    - 같은 이름 개수가 사전을 만든 해와 다르면 순번 키를 믿지 않고 ID를 붙이지 않는다(count_guard).
    - 이름 사전으로 한 공시의 두 행이 같은 ID를 받으면 둘 다 떼고(name_dup) 경고를 남긴다.
    """
    return _signed(_assign(doc, dictionary, kind))


def _check_dup_ids(df: pd.DataFrame) -> None:
    used = df[df["account_id"] != NO_ID]
    dup = used[used.duplicated(["corp_code", "fiscal_year", "sj_div", "account_id"], keep=False)]
    if len(dup):
        raise ValueError(f"한 공시에서 같은 ID가 여러 행: {dup[['fiscal_year', 'account_nm', 'account_id']].values.tolist()}")


def bridge(doc: pd.DataFrame, ref: pd.DataFrame, dictionary: pd.DataFrame, kind: str = "BS") -> pd.DataFrame:
    """다음 해 보고서의 전기 값(ref: account_id · amount · flip)과 금액으로 먼저 잇고, 나머지는 이름 사전.

    ref.flip: ref 금액이 원문 부호면 그 행의 부호 규칙, XBRL 부호면 False.
    금액 짝은 양쪽 모두 그 금액이 하나뿐일 때만 쓴다. 반대 부호로만 맞으면 flip을 뒤집는다.
    """
    tol = _tol(doc)
    out = _assign(doc, dictionary, kind)
    ref = ref.dropna(subset=["amount"])
    if "flip" not in ref:
        ref = ref.assign(flip=False)
    ref = ref[~ref["amount"].abs().duplicated(keep=False)]
    doc_amt = doc["amount"].dropna().astype("int64").abs()
    ref_amt = ref["amount"].astype("int64")
    fixed = set(out.loc[out["method"].isin(["core", "manual"]), "account_id"])
    for i, r in out.iterrows():
        # 이름 고정·작업자 승인 행은 금액 짝으로 덮지 않는다
        if out.at[i, "method"] in ("core", "manual", "rejected") or pd.isna(r["amount"]):
            continue
        a = int(r["amount"])
        if ((doc_amt - abs(a)).abs() <= tol).sum() != 1:
            continue
        same, opp = ref[(ref_amt - a).abs() <= tol], ref[(ref_amt + a).abs() <= tol]
        hit, toggled = (same, False) if len(same) else (opp, True)
        if len(hit) == 1 and hit["account_id"].iloc[0] not in fixed:
            out.at[i, "account_id"], out.at[i, "method"] = hit["account_id"].iloc[0], "amount"
            out.at[i, "flip"] = bool(hit["flip"].iloc[0]) != toggled
    # 금액 짝이 이름 사전과 같은 ID를 다른 행에 주면, 금액 짝을 믿고 이름 쪽을 뗀다
    taken = set(out.loc[out["method"] == "amount", "account_id"])
    clash = (out["method"] == "name") & out["account_id"].isin(taken)
    out.loc[clash, ["account_id", "method", "flip"]] = [NO_ID, "name_clash", False]
    return _signed(out)


# ---------- 대조 ----------

def compare(mapped: pd.DataFrame, xbrl: pd.DataFrame) -> pd.DataFrame:
    """ID가 붙은 원문 행을 같은 공시 XBRL과 비교. result: match · mismatch · missing_in_xbrl."""
    tol = _tol(mapped)
    x = xbrl[xbrl["account_id"] != NO_ID].drop_duplicates(["account_id", "amount"])
    x = x[~x["account_id"].duplicated(keep=False)].set_index("account_id")["amount"]  # IS·CIS 값이 다르면 대조에서 뺀다
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
                     "account_id": r.account_id, "method": getattr(r, "method", ""), "doc": r.amount, "xbrl": xv,
                     "result": res})
    return pd.DataFrame(rows, columns=["corp_code", "fiscal_year", "account_nm", "account_id", "method", "doc",
                                       "xbrl", "result"])


def core_missing(mapped: pd.DataFrame, kind: str = "BS") -> list[str]:
    """핵심 계정이 ID를 못 받은 공시. D-014: 비면 예외 대상."""
    need = {"BS": CORE, "IS": {"당기순이익": PROFIT_LOSS}, "CF": {}}[kind]
    errs = []
    for (c, y), g in mapped.groupby(["corp_code", "fiscal_year"]):
        for name, aid in need.items():
            if aid not in set(g["account_id"]):
                errs.append(f"{c} {y} {name}")
    return errs


def _summary(c, y, doc, mapped, cmp=None, kind="BS") -> dict:
    out = {"kind": kind, "corp_code": c, "fiscal_year": y, "rows_with_amount": int(doc["amount"].notna().sum()),
           "mapped": int((mapped["account_id"] != NO_ID).sum())}
    out |= {f"by_{k}": int(v) for k, v in mapped["method"].value_counts().items()}
    if cmp is not None:
        out |= {"match": int((cmp["result"] == "match").sum()), "mismatch": int((cmp["result"] != "match").sum())}
    out["core_missing"] = ",".join(core_missing(mapped, kind))
    return out


def holdout(docs: pd.DataFrame, pairs: pd.DataFrame, xbrl: pd.DataFrame,
            rmaps: dict[str, dict[str, str]], kind: str = "BS") -> tuple[pd.DataFrame, pd.DataFrame]:
    """XBRL 있는 해를 하나씩 빼고, XBRL 없는 해와 같은 방법(다음 해 전기 열 + 나머지 해 사전)으로 ID를 붙여 대조한다."""
    results, details = [], []
    for (c, y), doc in docs.groupby(["corp_code", "fiscal_year"]):
        rmap = rmaps.get(c, {})
        d, _ = build_dictionary(pairs[(pairs["corp_code"] == c) & (pairs["fiscal_year"] != y)], rmap)
        nxt = xbrl_rows(c, y + 1, kind)
        if nxt is not None:
            ref = pd.DataFrame({"account_id": _tr(nxt["account_id"], rmap), "amount": nxt["frmtrm"]})
            mapped = bridge(doc, ref, d, kind)
        else:
            mapped = apply(doc, d, kind)
        x = xbrl[(xbrl["corp_code"] == c) & (xbrl["fiscal_year"] == y)]
        cmp = compare(mapped, x.assign(account_id=_tr(x["account_id"], rmap)))
        results.append(_summary(c, y, doc, mapped, cmp, kind))
        details.append(cmp)
    return pd.DataFrame(results).fillna(0), pd.concat(details, ignore_index=True)


# ---------- XBRL 없는 해 ----------

def chain_back(corp_code: str, first_xbrl_year: int, years: list[int], pairs: pd.DataFrame,
               rmap: dict[str, str], docs: dict[int, tuple[str, Document] | None],
               kind: str = "BS") -> tuple[pd.DataFrame, pd.DataFrame]:
    """XBRL 첫해 바로 앞부터 거꾸로. 각 해의 기준(ref)은 다음 해 보고서의 전기 값이다.

    다음 해가 XBRL이면 그 frmtrm, 아니면 다음 해 원문 전기 열(같은 표·같은 행 순서라 당기 행의 ID를 그대로 받는다).
    잇고 난 해의 이름 → ID도 사전에 더해, 더 앞의 해가 이름으로 이어질 수 있게 한다.
    """
    want = list(range(min(years), first_xbrl_year))
    if sorted(years) != want:
        raise ValueError(f"{corp_code}: XBRL 없는 해는 XBRL 첫해({first_xbrl_year}) 바로 앞까지 이어져야 한다 {sorted(years)}")
    nxt = xbrl_rows(corp_code, first_xbrl_year, kind)
    if nxt is None:
        raise ValueError(f"{corp_code} {first_xbrl_year}: XBRL 원본 JSON이 없다")
    out, summary = [], []
    pool = pairs[pairs["corp_code"] == corp_code].copy()
    prev_mapped, prev_prior = None, None
    for y in sorted(years, reverse=True):
        if y >= first_xbrl_year:
            continue
        if docs.get(y) is None:  # 원문을 못 받은 해에서 멈춘다. 더 앞의 해는 이 해를 거쳐야 이어진다
            log.error("%s %s: 원문이 없어 %s년 이전은 잇지 않는다", corp_code, y, y)
            break
        rcept, body = docs[y]
        t = find_statement(body, kind)
        doc = parse_statement(t, kind, corp_code, y, rcept)
        if y + 1 == first_xbrl_year:
            ref = pd.DataFrame({"account_id": _tr(nxt["account_id"], rmap), "amount": nxt["frmtrm"]})
        else:
            # 다음 해 원문 전기 열(원문 부호) + 그 해 당기 행이 받은 ID·부호 규칙(같은 표·같은 행 순서)
            ref = prev_prior.merge(prev_mapped[["ord", "account_id", "flip"]], on="ord", how="left", validate="one_to_one")
            ref = ref.loc[ref["account_id_y"] != NO_ID, ["account_id_y", "amount", "flip"]].rename(
                columns={"account_id_y": "account_id"})
        d, _ = build_dictionary(pool, rmap)
        mapped = bridge(doc, ref, d, kind)
        summary.append(_summary(corp_code, y, doc, mapped, kind=kind))
        out.append(mapped)
        # 이 해 결과를 사전 풀에 더한다(금액 짝·이름 모두). 더 최근 해의 ID가 있으면 build_dictionary가 최근을 고른다
        # 이름 키·개수는 표 전체에서 센다(ID 붙은 행만 세면 같은 이름 개수가 달라진다)
        keyed = mapped.assign(name=name_keys(mapped).values, count=_name_counts(mapped).values)
        learned = keyed[keyed["account_id"] != NO_ID]
        pool = pd.concat([pool, learned[["corp_code", "fiscal_year", "name", "count", "account_id", "flip"]].assign(
            status="auto")], ignore_index=True)
        prev_mapped = mapped
        prev_prior = parse_statement(t, kind, corp_code, y - 1, rcept, period=1) if y - 1 in years else None
    return (pd.concat(out, ignore_index=True) if out else pd.DataFrame()), pd.DataFrame(summary).fillna(0)


# ---------- 실행 ----------

def run(corps: list[str], xbrl_years: list[int], back: dict[str, list[int]],
        kinds: tuple[str, ...] = ("BS", "IS", "CF"), refresh: bool = False) -> dict[str, pd.DataFrame]:
    fs = pd.read_parquet(OUT)
    got: dict[tuple[str, int], tuple[str, Document] | None] = {}

    def doc_of(c: str, y: int) -> tuple[str, Document] | None:
        """원문 본문을 한 번만 받아 읽고, 범용 층(문단·표·셀)을 저장한다."""
        if (c, y) not in got:
            try:
                rcept, data = fetch_document(c, y, force=refresh)
            except Exception as e:  # DART 시간 초과 등. 그 공시만 빼고 계속한다
                log.error("원문 못 받음 %s %s: %s", c, y, e)
                got[(c, y)] = None
                return None
            body = body_document(data, rcept)
            store.save(body, DOC_LAYER / rcept)
            got[(c, y)] = (rcept, body)
        return got[(c, y)]

    res: dict[str, list[pd.DataFrame]] = {}
    for kind in kinds:
        xbrl = fs[fs["sj_div"].isin(SJ[kind])]
        docs, pairs, rmaps = [], [], {}
        for c in corps:
            rmaps[c] = rename_map(c, sorted(xbrl.loc[xbrl["corp_code"] == c, "fiscal_year"].unique()), kind)
            for y in xbrl_years:
                x = xbrl[(xbrl["corp_code"] == c) & (xbrl["fiscal_year"] == y)]
                if x.empty or (d := doc_of(c, y)) is None:
                    continue
                rcept, body = d
                if rcept != x["rcept_no"].iloc[0]:
                    log.warning("%s %s 원문 판 %s != XBRL 판 %s", c, y, rcept, x["rcept_no"].iloc[0])
                doc = parse_statement(find_statement(body, kind), kind, c, y, rcept)
                docs.append(doc)
                pairs.append(pair(doc, x))
        docs, pairs = pd.concat(docs, ignore_index=True), pd.concat(pairs, ignore_index=True)
        built = [build_dictionary(pairs[pairs["corp_code"] == c], rmaps[c]) for c in corps]
        h, hd = holdout(docs, pairs, xbrl, rmaps, kind)
        part = {
            "pairs": pairs, "dictionary": pd.concat([b[0] for b in built]),
            "conflicts": pd.concat([b[1] for b in built]),
            "renames": pd.DataFrame([(c, o, n) for c, m in rmaps.items() for o, n in m.items()],
                                    columns=["corp_code", "old_id", "latest_id"]),
            "holdout": h, "holdout_detail": hd,
        }
        backs = [chain_back(c, int(xbrl.loc[xbrl["corp_code"] == c, "fiscal_year"].min()), years, pairs, rmaps[c],
                            {y: doc_of(c, y) for y in years}, kind) for c, years in back.items()]
        if backs:
            part |= {"back": pd.concat([b[1] for b in backs], ignore_index=True),
                     "back_rows": pd.concat([b[0] for b in backs], ignore_index=True)}
        for name, df in part.items():
            res.setdefault(name, []).append(df.assign(kind=kind) if "kind" not in df else df)
    return {name: pd.concat(dfs, ignore_index=True) for name, dfs in res.items()}


def save_document_rows(rows: pd.DataFrame) -> pd.DataFrame:
    """XBRL 없는 해의 원문 행을 D-011 스키마로 저장한다. 불변식 검사를 통과해야 쓴다."""
    out = rows.drop(columns=["method", "kind", "flip"], errors="ignore")
    validate(out)
    DOC_OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(DOC_OUT, index=False)
    log.info("저장 %s 행=%d (사전 %s)", DOC_OUT, len(out), DICT_VERSION)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corps", type=int, default=5)
    ap.add_argument("--years", default="2023-2025", help="XBRL 대조 연도")
    ap.add_argument("--back", default="00688996:2015-2022", help="XBRL 없는 해 corp:연도범위, 비우면 생략")
    ap.add_argument("--refresh", action="store_true", help="공시목록을 다시 받아 새 정정판을 반영한다")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    lo, _, hi = a.years.partition("-")
    back = {}
    if a.back:
        c, _, rng = a.back.partition(":")
        b0, _, b1 = rng.partition("-")
        back[c] = list(range(int(b0), int(b1 or b0) + 1))
    out = run(list(dart.CORPS)[: a.corps], list(range(int(lo), int(hi or lo) + 1)), back, refresh=a.refresh)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in out.items():
        df.to_csv(REPORT_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")
    h = out["holdout"]
    log.info("XBRL 대조(한 해 빼기) 불일치 %d건, 핵심 계정 누락 %d공시, 이름 바뀐 ID %d개",
             h["mismatch"].sum(), (h["core_missing"] != "").sum(), len(out["renames"]))
    if "back_rows" in out:
        save_document_rows(out["back_rows"])


if __name__ == "__main__":
    main()
