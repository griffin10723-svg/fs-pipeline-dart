"""OpenDART 호출과 응답 변환. 파일 입출력은 collect.py가 맡는다."""

import logging
import os
import re

import pandas as pd
import requests
from dotenv import find_dotenv, load_dotenv

log = logging.getLogger(__name__)

BASE = "https://opendart.fss.or.kr/api"
ANNUAL = "11011"  # 사업보고서
NO_DATA = "013"  # 금융업 2022 이전 등 (D-009)

# 회계판단: D-008 v0 기업 5곳 (고유번호)
CORPS = {
    "00126380": "삼성전자",
    "00164779": "SK하이닉스",
    "00258801": "카카오",
    "00688996": "KB금융",
    "00159193": "한국전력",
}

# D-011 유일성 키. account_detail은 SCE의 자본 구성요소 열을 가른다
KEY_COLS = ["corp_code", "fiscal_year", "sj_div", "account_id", "ord", "account_detail"]


class RceptMismatch(Exception):
    """응답의 접수번호가 공시목록의 마지막 정정본과 다르다 (D-004)."""


class DartRequestError(Exception):
    """DART 요청 실패. 메시지에서 인증키를 가렸다."""


_KEY_IN_URL = re.compile(r"(crtfc_key=)[^&\s'\")]+")


def redact(text: str) -> str:
    """URL·에러 메시지 속 인증키를 ***로 바꾼다."""
    return _KEY_IN_URL.sub(r"\1***", text)


def _get(endpoint: str, params: dict) -> requests.Response:
    """GET 후 상태 검사. requests 에러는 URL(키 포함)을 담으므로 가린 메시지로 바꿔 던진다."""
    try:
        r = requests.get(f"{BASE}/{endpoint}", params={"crtfc_key": _api_key()} | params, timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        # from None: 원래 예외(키 포함)를 traceback에 남기지 않는다
        raise DartRequestError(f"{endpoint}: {type(e).__name__}: {redact(str(e))}") from None
    return r


def _api_key() -> str:
    # 스크립트 위치가 아니라 실행 폴더에서 .env를 찾는다
    load_dotenv(find_dotenv(usecwd=True))
    return os.environ["DART_API_KEY"]


def fetch_fs(corp_code: str, year: int) -> dict:
    """연결(CFS) 전체 재무제표. 회계판단: D-001."""
    r = _get("fnlttSinglAcntAll.json", {
        "corp_code": corp_code, "bsns_year": year, "reprt_code": ANNUAL, "fs_div": "CFS",
    })
    return r.json()


def last_rcept_no(corp_code: str, year: int) -> str:
    """해당 사업연도 사업보고서의 마지막(정정 포함) 접수번호."""
    # 정정은 1년 뒤에도 나온다(KB 2024). 조회 끝을 오늘로 둔다
    r = _get("list.json", {
        "corp_code": corp_code, "bgn_de": f"{year + 1}0101",
        "end_de": pd.Timestamp.today().strftime("%Y%m%d"),
        "pblntf_ty": "A", "page_count": 100,
    })
    body = r.json()
    if body["status"] != "000":
        raise RuntimeError(f"list.json {corp_code} {year}: {body['status']} {body['message']}")
    # 12월 결산만 다룬다(결산월 변경은 Should). 접수번호는 날짜로 시작하므로 max가 최신이다
    hits = [
        x["rcept_no"] for x in body["list"]
        if "사업보고서" in x["report_nm"] and f"({year}.12)" in x["report_nm"]
    ]
    if not hits:
        raise RuntimeError(f"공시목록에 {corp_code} {year} 사업보고서가 없다")
    return max(hits)


def check_rcept(rows: list[dict], expected: str) -> str:
    """응답 전 행의 접수번호가 하나이고 expected와 같은지 확인한다."""
    got = {x["rcept_no"] for x in rows}
    if got != {expected}:
        raise RceptMismatch(f"응답 {sorted(got)} != 공시목록 마지막 {expected}")
    return expected


_INT = re.compile(r"-?\d+")


def to_amount(s: str):
    """금액 문자열을 원 단위 정수로. 빈 값은 NA, 그 밖에 숫자가 아니면 예외 (D-011)."""
    s = s.strip().replace(",", "")
    if s in ("", "-"):  # 소계 머리글 행은 금액이 비어 있다
        return pd.NA
    if not _INT.fullmatch(s):
        raise ValueError(f"금액 변환 불가: {s!r}")
    return int(s)


def to_frame(rows: list[dict]) -> pd.DataFrame:
    """응답 list를 D-011 스키마의 DataFrame으로. 계정은 거르지 않는다 (D-003)."""
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "corp_code": df["corp_code"],
        "fiscal_year": df["bsns_year"].astype(int),
        "sj_div": df["sj_div"],
        "account_id": df["account_id"],
        "ord": df["ord"].astype(int),
        "account_nm": df["account_nm"],
        "account_detail": df["account_detail"],
        "amount": pd.array([to_amount(x) for x in df["thstrm_amount"]], dtype="Int64"),
        "currency": df["currency"],
        "rcept_no": df["rcept_no"],
        "reprt_code": df["reprt_code"],
        "source": "xbrl",  # 원문 파싱 행(document)과 구분한다 (D-014)
    })
    return out
