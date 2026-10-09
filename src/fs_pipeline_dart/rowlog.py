"""함수 단위 행 수 로그 (forge:dev-rules 2장, 작업자 결정 2026-10-10).

거르고 합치는 함수의 들어온 행 수·나간 행 수를 남긴다. 함수 안 필터 줄마다 붙이지 않는다.
행이 어느 단계에서 늘거나 줄었는지는 이 로그로 좁히고, 줄 단위는 그 함수 안에서 본다.
"""

import functools
import logging

import pandas as pd

log = logging.getLogger(__name__)


def _rows(x) -> int | None:
    """DataFrame이면 그 행 수, 튜플이면 첫 DataFrame의 행 수."""
    if isinstance(x, pd.DataFrame):
        return len(x)
    if isinstance(x, tuple):
        return next((len(v) for v in x if isinstance(v, pd.DataFrame)), None)
    return None


def rows_logged(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        rows_in = next((n for a in (*args, *kwargs.values()) if (n := _rows(a)) is not None), None)
        out = fn(*args, **kwargs)
        log.info("rows fn=%s in=%s out=%s", fn.__qualname__, rows_in, _rows(out))
        return out
    return wrapper
