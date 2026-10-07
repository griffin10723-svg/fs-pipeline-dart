"""계정 매핑: 금액 짝짓기가 모호하면 자동으로 짝짓지 않고, 대조는 한 해 빼기로 한다 (D-014)."""

import pandas as pd

from fs_pipeline_dart import mapping as m
from fs_pipeline_dart.validate import NO_ID

M = 1_000_000


def _doc(year, rows, corp="C", sj="BS"):
    return pd.DataFrame([{"corp_code": corp, "fiscal_year": year, "sj_div": sj, "ord": i, "account_nm": n, "amount": a}
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


def test_dictionary_takes_latest_year_id():
    # D-005 부분: 같은 이름의 ID가 해마다 다르면 최근 연도 ID. 충돌은 기록만 한다
    pairs = pd.concat([
        m.pair(_doc(2023, [("현금", 10 * M)]), _xbrl(2023, [("id_a", 10 * M)])),
        m.pair(_doc(2024, [("현금", 11 * M)]), _xbrl(2024, [("id_b", 11 * M)])),
    ])
    d, c = m.build_dictionary(pairs)
    assert d[["name", "account_id", "year"]].values.tolist() == [["현금", "id_b", 2024]]
    assert c.values.tolist() == [["C", "현금", "id_a;id_b"]]
    # 옛 ID가 새 ID로 이어지면 충돌이 아니다
    _, c2 = m.build_dictionary(pairs, {"id_a": "id_b"})
    assert c2.empty


def _dict(rows):
    cols = ["corp_code", "name", "account_id", "year", "count"]
    return pd.DataFrame([{"corp_code": "C", "name": n, "account_id": i, "year": 2024, "count": k}
                         for n, i, k in rows], columns=cols)


def test_apply_two_names_same_id_assigns_neither():
    # 카카오 2023: '파생상품자산(유동)'과 '파생상품자산'이 최근 연도 ID로 같은 ID를 받는다
    out = m.apply(_doc(2024, [("현금", 1 * M), ("현금성자산", 2 * M)]), _dict([("현금", "id", 1), ("현금성자산", "id", 1)]))
    assert out[["account_id", "method"]].values.tolist() == [[NO_ID, "name_dup"], [NO_ID, "name_dup"]]


def test_count_guard_when_same_name_count_changes():
    # 사전 해에는 '충당부채'가 둘(유동·비유동). 이번 해 하나뿐이면 순번 키를 믿지 않는다
    d = _dict([("충당부채", "cur", 2), ("충당부채#2", "noncur", 2)])
    out = m.apply(_doc(2022, [("충당부채", 5 * M)]), d)
    assert out[["account_id", "method"]].values.tolist() == [[NO_ID, "count_guard"]]
    out = m.apply(_doc(2022, [("충당부채", 5 * M), ("충당부채", 6 * M)]), d)
    assert out["account_id"].tolist() == ["cur", "noncur"]


def test_core_fixed_by_name():
    out = m.apply(_doc(2022, [("자 산 총 계", 9 * M)]), _dict([]))
    assert out[["account_id", "method"]].values.tolist() == [["ifrs-full_Assets", "core"]]
    out = m.apply(_doc(2022, [("XⅢ. 당기순이익", 9 * M), ("계속영업당기순이익", 9 * M)], sj="CIS"), _dict([]), "IS")
    assert out["account_id"].tolist() == ["ifrs-full_ProfitLoss", NO_ID]


def test_bridge_prefers_next_year_comparative_amount():
    # 이름 사전은 '예치금'→old. 다음 해 전기 열에서 같은 금액이 new_id면 금액 짝을 쓴다
    doc = _doc(2022, [("예치금", 7 * M), ("대출금", 30 * M), ("기타", 4 * M)])
    ref = pd.DataFrame({"account_id": ["new_id", "loan_restated"], "amount": [7 * M, 33 * M]}).astype({"amount": "Int64"})
    out = m.bridge(doc, ref, _dict([("예치금", "old", 1), ("대출금", "loan", 1)]))
    # 재작성으로 금액이 다른 대출금은 이름 사전으로 붙는다
    assert out[["account_id", "method"]].values.tolist() == [["new_id", "amount"], ["loan", "name"], [NO_ID, "none"]]


def test_bridge_drops_name_id_taken_by_amount_pair():
    doc = _doc(2022, [("A", 7 * M), ("B", 9 * M)])
    ref = pd.DataFrame({"account_id": ["x"], "amount": [7 * M]}).astype({"amount": "Int64"})
    out = m.bridge(doc, ref, _dict([("B", "x", 1)]))
    assert out[["account_id", "method"]].values.tolist() == [["x", "amount"], [NO_ID, "name_clash"]]


def test_same_name_twice_gets_occurrence_key():
    # 삼성전자 '충당부채'는 유동·비유동 두 번 나온다
    p = m.pair(_doc(2023, [("충당부채 (주19)", 10 * M), ("충당부채 (주19)", 13 * M)]),
               _xbrl(2023, [("ifrs-full_CurrentProvisions", 10 * M), ("ifrs-full_NoncurrentProvisions", 13 * M)]))
    assert p[["name", "account_id"]].values.tolist() == [
        ["충당부채", "ifrs-full_CurrentProvisions"], ["충당부채#2", "ifrs-full_NoncurrentProvisions"]]


def test_pair_and_apply_flip_sign_to_xbrl_convention():
    # KB금융: 원문 일반관리비 −6.9조, XBRL 6.9조. 짝은 반대 부호로 찾고 금액은 XBRL 부호로 낸다
    p = m.pair(_doc(2024, [("Ⅵ. 일반관리비", -69 * M)], sj="CIS"), _xbrl(2024, [("sga", 69 * M)]))
    assert p[["status", "account_id", "flip"]].values.tolist() == [["auto", "sga", True]]
    d, _ = m.build_dictionary(p)
    out = m.apply(_doc(2015, [("V. 일반관리비", -45 * M)], sj="CIS"), d, "IS")
    assert out[["account_id", "amount"]].values.tolist() == [["sga", 45 * M]]


def test_bridge_keeps_doc_prior_sign_rule():
    # 다음 해 원문 전기 열(원문 부호 −7)이 flip=True ID를 받았으면 이번 해 −7도 같은 ID·같은 부호 규칙
    ref = pd.DataFrame({"account_id": ["sga"], "amount": [-7 * M], "flip": [True]}).astype({"amount": "Int64"})
    out = m.bridge(_doc(2021, [("일반관리비", -7 * M)], sj="CIS"), ref, _dict([]), "IS")
    assert out[["account_id", "method", "amount"]].values.tolist() == [["sga", "amount", 7 * M]]


def test_manual_mapping_only_when_approved(tmp_path):
    f = tmp_path / "manual.csv"
    f.write_text("corp_code,kind,name,account_id,flip,status,proposed_by,note\n"
                 "C,IS,순이자이익,nii,False,approved,AI,\n"
                 "C,IS,순수수료이익,fee,False,proposed,AI,\n", encoding="utf-8")
    man = m.manual_dictionary(f)
    out = m.apply(_doc(2015, [("Ⅰ. 순이자이익", 6 * M), ("Ⅱ. 순수수료이익", 1 * M)], sj="CIS"), _dict([]), "IS")
    assert out["method"].tolist() == ["none", "none"]  # 저장소 파일은 아직 승인 전
    out = m._signed(m._assign(_doc(2015, [("Ⅰ. 순이자이익", 6 * M), ("Ⅱ. 순수수료이익", 1 * M)], sj="CIS"),
                              _dict([]), "IS", man))
    assert out[["account_id", "method"]].values.tolist() == [["nii", "manual"], [NO_ID, "none"]]
