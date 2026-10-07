"""문서 모델을 parquet으로 저장하고 다시 읽는다 (범용 층 저장).

문단·표·셀 세 파일. 셀은 원표 그대로(병합 정보 포함) 두고, 격자 펼치기는 읽는 쪽이 `Table.grid()`로 한다.
주석 표(N2·N9·M1)와 본문 문단(P7)이 이 파일을 읽는다.
"""

from pathlib import Path

import pandas as pd

from docparse.model import Cell, Document, Paragraph, Table

FILES = ("paragraphs", "tables", "cells")


def to_frames(doc: Document) -> dict[str, pd.DataFrame]:
    paras = pd.DataFrame(
        [{"source": doc.source, "seq": i, "section": list(p.section), "text": p.text}
         for i, p in enumerate(doc.paragraphs)],
        columns=["source", "seq", "section", "text"],
    )
    tables = pd.DataFrame(
        [{"source": doc.source, "table": t.index, "section": list(t.section), "unit_text": t.unit_text}
         for t in doc.tables],
        columns=["source", "table", "section", "unit_text"],
    )
    cells = pd.DataFrame(
        [{"source": doc.source, "table": t.index, "row": r, "pos": c, "text": cell.text,
          "rowspan": cell.rowspan, "colspan": cell.colspan, "header": cell.header}
         for t in doc.tables for r, row in enumerate(t.rows) for c, cell in enumerate(row)],
        columns=["source", "table", "row", "pos", "text", "rowspan", "colspan", "header"],
    )
    return {"paragraphs": paras, "tables": tables, "cells": cells}


def save(doc: Document, folder: Path) -> dict[str, Path]:
    """folder/{paragraphs,tables,cells}.parquet. 같은 폴더에 다시 쓰면 덮어쓴다."""
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, df in to_frames(doc).items():
        out[name] = folder / f"{name}.parquet"
        df.to_parquet(out[name], index=False)
    return out


def load(folder: Path) -> Document:
    """save()의 역. 문서 하나만 담긴 폴더를 읽는다."""
    paras, tables, cells = (pd.read_parquet(folder / f"{n}.parquet") for n in FILES)
    sources = set(paras["source"]) | set(tables["source"])
    if len(sources) > 1:
        raise ValueError(f"한 폴더에 문서가 여럿이다: {sorted(sources)}")
    rows: dict[int, dict[int, list[Cell]]] = {}
    for x in cells.sort_values(["table", "row", "pos"]).itertuples(index=False):
        rows.setdefault(x.table, {}).setdefault(x.row, []).append(
            Cell(text=x.text, rowspan=int(x.rowspan), colspan=int(x.colspan), header=bool(x.header)))
    return Document(
        source=sources.pop() if sources else "",
        paragraphs=[Paragraph(section=tuple(p.section), text=p.text) for p in paras.itertuples(index=False)],
        tables=[
            Table(section=tuple(t.section), rows=[rows.get(t.table, {})[r] for r in sorted(rows.get(t.table, {}))],
                  unit_text=t.unit_text if isinstance(t.unit_text, str) else None,  # 전부 None이면 NaN으로 읽힌다
                  index=int(t.table))
            for t in tables.sort_values("table").itertuples(index=False)
        ],
    )
