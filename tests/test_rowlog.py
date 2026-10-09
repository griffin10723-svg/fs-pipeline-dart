"""함수 단위 행 수 로그가 들어온·나간 행 수를 남기는지 본다."""

import logging

import pandas as pd

from fs_pipeline_dart.rowlog import rows_logged


@rows_logged
def _keep_positive(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    return df[df["x"] > 0], "note"


def test_logs_rows_in_and_out(caplog):
    with caplog.at_level(logging.INFO, logger="fs_pipeline_dart.rowlog"):
        out, _ = _keep_positive(pd.DataFrame({"x": [1, -1, 2]}))
    assert len(out) == 2
    assert "fn=_keep_positive in=3 out=2" in caplog.text
