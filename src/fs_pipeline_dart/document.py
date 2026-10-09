"""사업보고서 원문(`document.xml` zip) 받기. 본문을 가진 마지막 판을 쓴다 (D-004)."""

import json
import logging
import re
import zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd

from docparse.dart_xml import xml_members
from fs_pipeline_dart import dart

log = logging.getLogger(__name__)

RAW_DOC = Path("data/raw/document")
RCEPT = re.compile(r"\d{14}")
BODY_MARK = re.compile(rb'<DOCUMENT-NAME\s+ACODE="11011"')  # 사업보고서 본문 (감사보고서는 00760·00761)


def report_versions(corp_code: str, year: int, force: bool = False) -> list[str]:
    """해당 사업연도 사업보고서의 모든 판(원공시·정정) 접수번호, 최신부터.

    `dart.last_rcept_no`와 같은 공시목록 조건이다. 그 함수는 마지막 1판만 돌려줘서 따로 둔다.
    목록은 파일로 남겨 다시 묻지 않는다. 새 정정을 반영하려면 force.
    """
    cache = RAW_DOC / f"versions_{corp_code}_{year}.json"
    if cache.exists() and not force:
        return json.loads(cache.read_text(encoding="utf-8"))
    r = dart._get("list.json", {
        "corp_code": corp_code, "bgn_de": f"{year + 1}0101",
        "end_de": pd.Timestamp.today().strftime("%Y%m%d"),
        "pblntf_ty": "A", "page_count": 100,
    })
    body = r.json()
    if body["status"] != "000":
        raise RuntimeError(f"list.json {corp_code} {year}: {body['status']} {body['message']}")
    if int(body.get("total_page", 1)) > 1:  # 한 쪽(100건)을 넘으면 앞 판을 놓친다. 넘는 회사가 생기면 쪽 넘김을 넣는다
        raise RuntimeError(f"list.json {corp_code} {year}: 공시 {body['total_count']}건이 한 쪽을 넘는다")
    hits = sorted(
        (x["rcept_no"] for x in body["list"]
         if "사업보고서" in x["report_nm"] and f"({year}.12)" in x["report_nm"]),
        reverse=True,
    )
    if not hits:
        raise RuntimeError(f"공시목록에 {corp_code} {year} 사업보고서가 없다")
    RAW_DOC.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(hits), encoding="utf-8")
    return hits


def body_xml(data: bytes) -> tuple[str, bytes] | None:
    """zip 안 사업보고서 본문 xml (파일명, 바이트). 없으면 None, 둘 이상이면 예외.

    [첨부정정]은 감사보고서(00760·00761)만 담는다. 머리 2,000바이트만 풀어 본문인지 본다.
    """
    with zipfile.ZipFile(BytesIO(data)) as zf:
        hits = []
        for i in xml_members(zf):
            with zf.open(i) as f:
                if BODY_MARK.search(f.read(2000)):
                    hits.append(i)
        if len(hits) > 1:
            raise RuntimeError(f"본문 xml이 {len(hits)}개 {[i.filename for i in hits]}")
        return (hits[0].filename.lstrip("/"), zf.read(hits[0])) if hits else None


def has_body(data: bytes) -> bool:
    return body_xml(data) is not None


class DartUnavailable(RuntimeError):
    """DART 시스템 점검(status 800). 원문 문제가 아니므로 점검이 끝난 뒤 다시 돌린다."""


_STATUS = re.compile(rb"<status>(\d+)</status>\s*<message>(.*?)</message>", re.S)


def _status_error(rcept_no: str, data: bytes) -> RuntimeError:
    """zip 대신 온 DART 오류 응답을 읽을 수 있는 예외로 바꾼다."""
    m = _STATUS.search(data[:500])
    if not m:
        return RuntimeError(f"document.xml {rcept_no}: zip이 아니다 {data[:200]!r}")
    status, message = m[1].decode(), m[2].decode("utf-8", "replace").strip()
    cls = DartUnavailable if status == "800" else RuntimeError
    return cls(f"document.xml {rcept_no}: DART status {status} {message}")


def _download(rcept_no: str) -> bytes | None:
    """zip 바이트. DART가 '파일 없음'(014)을 주면 None (KB금융 2025 정정 `20260619000667`)."""
    if not RCEPT.fullmatch(rcept_no):  # 파일 이름에 들어가므로 형식을 확인한다
        raise ValueError(f"접수번호 형식이 아니다: {rcept_no!r}")
    path = RAW_DOC / f"{rcept_no}.zip"
    if path.exists():
        return path.read_bytes()
    data = dart._get("document.xml", {"rcept_no": rcept_no}).content
    if b"<status>014</status>" in data[:300]:
        return None
    if not data.startswith(b"PK"):
        raise _status_error(rcept_no, data)
    RAW_DOC.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def fetch_document(corp_code: str, year: int, force: bool = False) -> tuple[str, bytes]:
    """본문을 가진 마지막 판의 (접수번호, zip). 회계판단: D-004.

    마지막 판에 본문이 없거나 원문 파일이 없으면(014) 한 판씩 이전으로 내려간다. 어느 판을 썼는지는 접수번호로 남긴다.
    """
    versions = report_versions(corp_code, year, force)
    for i, rcept in enumerate(versions):
        data = _download(rcept)
        if data is None:
            log.info("%s %s: %s는 원문 파일 없음(014)", corp_code, year, rcept)
            continue
        if has_body(data):
            if i:
                log.warning("%s %s: 최근 %d판에 본문이 없어 %s를 쓴다 (마지막 %s)",
                            corp_code, year, i, rcept, versions[0])
            return rcept, data
        log.info("%s %s: %s는 본문 없음(첨부정정)", corp_code, year, rcept)
    raise RuntimeError(f"{corp_code} {year}: 본문을 가진 판이 없다 {versions}")
