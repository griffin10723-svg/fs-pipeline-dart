"""v0 수집: 기업×연도마다 원본 JSON을 보관하고 parquet 하나로 모은다 (D-011)."""

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from fs_pipeline_dart import dart
from fs_pipeline_dart.rowlog import rows_logged
from fs_pipeline_dart.validate import validate

log = logging.getLogger(__name__)

RAW = Path("data/raw")
OUT = Path("data/processed/fs_long.parquet")


def collect_one(corp_code: str, year: int, force: bool = False) -> Path | None:
    """원본 JSON을 받아 둔다. 이미 있으면 건너뛴다. 데이터가 없으면 None."""
    path = RAW / f"{corp_code}_{year}.json"
    if path.exists() and not force:
        log.info("있음, 건너뜀 %s", path.name)
        return path

    body = dart.fetch_fs(corp_code, year)
    if body["status"] == dart.NO_DATA:
        # 금융업 2022 이전 등. 조용히 비우지 않고 기록을 남긴다 (D-009)
        log.warning("데이터 없음(013) %s %s", dart.CORPS.get(corp_code, corp_code), year)
        return None
    if body["status"] != "000":
        raise RuntimeError(f"{corp_code} {year}: {body['status']} {body['message']}")

    expected = dart.last_rcept_no(corp_code, year)
    dart.check_rcept(body["list"], expected)  # 회계판단: D-004

    RAW.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    meta = {
        "corp_code": corp_code, "year": year, "rows": len(body["list"]), "rcept_no": expected,
        "last_rcept_no_match": True,
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    path.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    log.info("수집 %s %s 행=%d rcept_no=%s", dart.CORPS.get(corp_code), year, meta["rows"], expected)
    return path


@rows_logged
def build_parquet(paths: list[Path]) -> pd.DataFrame:
    """원본 JSON들을 합쳐 parquet으로 저장한다. 합치기 전후 행 수를 기록한다."""
    frames = []
    for p in paths:
        df = dart.to_frame(json.loads(p.read_text(encoding="utf-8"))["list"])
        log.info("변환 %s 행=%d", p.name, len(df))
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    # merge가 아니라 concat이라 행 수가 합과 같아야 한다. 다르면 코드 오류다
    assert len(out) == sum(len(f) for f in frames)
    validate(out)  # 위반이 있으면 parquet을 쓰기 전에 멈춘다
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    log.info("저장 %s 행=%d", OUT, len(out))
    return out


def _years(s: str) -> list[int]:
    a, _, b = s.partition("-")
    return list(range(int(a), int(b or a) + 1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corps", type=int, default=5, help="D-008 기업 앞에서 N곳")
    ap.add_argument("--years", default="2023-2025")
    ap.add_argument("--force", action="store_true", help="이미 받은 원본도 다시 받는다")
    a = ap.parse_args()

    Path("outputs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("outputs/collect.log", encoding="utf-8")],
    )
    corps = list(dart.CORPS)[: a.corps]
    paths = [
        p for c in corps for y in _years(a.years)
        if (p := collect_one(c, y, a.force)) is not None
    ]
    build_parquet(paths)


if __name__ == "__main__":
    main()
