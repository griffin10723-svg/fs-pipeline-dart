"""사업보고서 원문(`document.xml` zip) 받기. 본문을 가진 마지막 판을 쓴다 (D-004)."""

import logging
import re
import zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd

from fs_pipeline_dart import dart

log = logging.getLogger(__name__)

RAW_DOC = Path("data/raw/document")
BODY_MARK = re.compile(rb'<DOCUMENT-NAME\s+ACODE="11011"')  # 사업보고서 본문 (감사보고서는 00760·00761)


def report_versions(corp_code: str, year: int) -> list[str]:
    """해당 사업연도 사업보고서의 모든 판(원공시·정정) 접수번호, 최신부터.

    `dart.last_rcept_no`와 같은 공시목록 조건이다. 그 함수는 마지막 1판만 돌려줘서 따로 둔다.
    """
    r = dart._get("list.json", {
        "corp_code": corp_code, "bgn_de": f"{year + 1}0101",
        "end_de": pd.Timestamp.today().strftime("%Y%m%d"),
        "pblntf_ty": "A", "page_count": 100,
    })
    body = r.json()
    if body["status"] != "000":
        raise RuntimeError(f"list.json {corp_code} {year}: {body['status']} {body['message']}")
    hits = sorted(
        (x["rcept_no"] for x in body["list"]
         if "사업보고서" in x["report_nm"] and f"({year}.12)" in x["report_nm"]),
        reverse=True,
    )
    if not hits:
        raise RuntimeError(f"공시목록에 {corp_code} {year} 사업보고서가 없다")
    return hits


def has_body(data: bytes) -> bool:
    """zip 안에 사업보고서 본문 xml이 있는가. [첨부정정]은 감사보고서만 담는다."""
    with zipfile.ZipFile(BytesIO(data)) as zf:
        return any(BODY_MARK.search(zf.read(n)[:2000]) for n in zf.namelist() if n.lower().endswith(".xml"))


def _download(rcept_no: str) -> bytes:
    path = RAW_DOC / f"{rcept_no}.zip"
    if path.exists():
        return path.read_bytes()
    data = dart._get("document.xml", {"rcept_no": rcept_no}).content
    if not data.startswith(b"PK"):
        raise RuntimeError(f"document.xml {rcept_no}: zip이 아니다 {data[:200]!r}")
    RAW_DOC.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def fetch_document(corp_code: str, year: int) -> tuple[str, bytes]:
    """본문을 가진 마지막 판의 (접수번호, zip). 회계판단: D-004.

    마지막 판에 본문이 없으면 한 판씩 이전으로 내려간다. 어느 판을 썼는지는 접수번호로 남긴다.
    """
    versions = report_versions(corp_code, year)
    for i, rcept in enumerate(versions):
        data = _download(rcept)
        if has_body(data):
            if i:
                log.warning("%s %s: 최근 %d판에 본문이 없어 %s를 쓴다 (마지막 %s)",
                            corp_code, year, i, rcept, versions[0])
            return rcept, data
        log.info("%s %s: %s는 본문 없음(첨부정정)", corp_code, year, rcept)
    raise RuntimeError(f"{corp_code} {year}: 본문을 가진 판이 없다 {versions}")
