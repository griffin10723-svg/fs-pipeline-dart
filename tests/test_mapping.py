"""계정 매핑: 금액 짝짓기가 모호하면 자동으로 짝짓지 않고, 대조는 한 해 빼기로 한다 (D-014)."""

import pandas as pd
import pytest

from fs_pipeline_dart import mapping as m
from fs_pipeline_dart.validate import NO_ID

M = 1_000_000


def _doc(year, rows, corp="C"):
    return pd.DataFrame([{"corp_code": corp, "fiscal_year": year, "ord": i, "account_nm": n, "amount": a}
                         for i, (n, a) in enumerate(rows)]).astype({"amount": "Int64"})


def _xbrl(year, rows, corp="C"):
    return pd.DataFrame([{"corp_code": corp, "fiscal_year": year, "account_id": i, "amount": a}
                         for i, a in rows]).astype({"amount": "Int64"})


def test_pair_statuses():
    doc = _doc(2024, [("자 산", None), ("현금 (주4)", 10 * M), ("기타A", 5 * M), ("기타B", 5 * M),
                      ("이상한 계정", 7 * M), ("자산총계", 100 * M)])
    x = _xbrl(2024, [("ifrs-full_Cash", 10 * M + 400_000), ("x_A", 5 * M), ("ifrs-full_Assets", 100 * M),
                     ("ifrs-full_Assets2", 100 * M), (NO_ID, 7 * M)])
    p = m.pair(doc, x).set_index("account_nm")
    assert p.loc["자 산", "status"] == "no_amount"
    assert p.loc["현금 (주4)", ["status", "account_id", "name"]].tolist() == ["auto", "ifrs-full_Cash", "현금"]
    assert p.loc["기타A", "status"] == "dup_doc"  # 원문에 같은 금액이 둘
    assert p.loc["이상한 계정", "status"] == "none"  # 표준 ID 없는 XBRL 행과는 짝짓지 않는다
    assert p.loc["자산총계", "status"] == "dup_xbrl"


def test_dictionary_conflict_across_years():
    pairs = pd.concat([
        m.pair(_doc(2023, [("현금", 10 * M)]), _xbrl(2023, [("id_a", 10 * M)])),
        m.pair(_doc(2024, [("현금", 11 * M)]), _xbrl(2024, [("id_b", 11 * M)])),
        m.pair(_doc(2024, [("예치금", 3 * M)]), _xbrl(2024, [("id_c", 3 * M)])),
    ])
    d, c = m.build_dictionary(pairs)
    assert d[["name", "account_id"]].values.tolist() == [["예치금", "id_c"]]
    assert c.values.tolist() == [["C", "현금", "id_a;id_b"]]


def test_apply_two_rows_same_id_fails():
    d = pd.DataFrame([{"corp_code": "C", "name": "현금", "account_id": "id"},
                      {"corp_code": "C", "name": "현금성자산", "account_id": "id"}])
    with pytest.raises(ValueError, match="같은 ID"):
        m.apply(_doc(2024, [("현금", 1 * M), ("현금성자산", 2 * M)]), d)


def test_holdout_detects_relabelled_account():
    # 2023·2024는 '현금'이 id_cash, 2025에 같은 이름으로 다른 금액 → 빠진 해 대조에서 불일치로 잡힌다
    years = {2023: 10, 2024: 11, 2025: 12}
    docs = pd.concat([_doc(y, [("현금", v * M), ("자산총계", 100 * M + y)]) for y, v in years.items()])
    xb = pd.concat([_xbrl(y, [("id_cash", (v if y != 2025 else 99) * M), ("ifrs-full_Assets", 100 * M + y)])
                    for y, v in years.items()])
    pairs = pd.concat([m.pair(docs[docs.fiscal_year == y], xb[xb.fiscal_year == y]) for y in years])
    h = m.holdout(docs, pairs, xb).set_index("fiscal_year")
    assert h.loc[2025, "mismatch"] == 1
    assert h.loc[2023, "mismatch"] == 0
    assert "부채총계" in h.loc[2023, "core_missing"]
    assert "자산총계" not in h.loc[2023, "core_missing"]  # 핵심 3계정은 이름으로 고정


def test_same_name_twice_gets_occurrence_key():
    # 삼성전자 '충당부채'는 유동·비유동 두 번 나온다
    p = m.pair(_doc(2023, [("충당부채 (주19)", 10 * M), ("충당부채 (주19)", 13 * M)]),
               _xbrl(2023, [("ifrs-full_CurrentProvisions", 10 * M), ("ifrs-full_NoncurrentProvisions", 13 * M)]))
    assert p[["name", "account_id"]].values.tolist() == [
        ["충당부채", "ifrs-full_CurrentProvisions"], ["충당부채#2", "ifrs-full_NoncurrentProvisions"]]
