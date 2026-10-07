"""범용 층 저장: parquet으로 쓰고 다시 읽으면 같은 문서 모델이 된다."""

import pytest
from test_dart_xml import DOC

from docparse.dart_xml import read_xml
from docparse.store import load, save, to_frames


def test_roundtrip(tmp_path):
    doc = read_xml(DOC.encode(), "20231005000471/20231005000471.xml")
    save(doc, tmp_path)
    back = load(tmp_path)
    assert back == doc
    assert back.tables[1].grid()[2] == ["자산총계", "701,170,848", "5"]


def test_cells_keep_merge_info():
    cells = to_frames(read_xml(DOC.encode(), "x"))["cells"]
    head = cells[(cells["table"] == 1) & (cells["row"] == 0)]
    assert head[["text", "rowspan", "colspan", "header"]].values.tolist() == [
        ["과 목", 2, 1, True], ["제 15기말", 1, 2, True]]


def test_two_documents_in_one_folder_fail(tmp_path):
    save(read_xml(DOC.encode(), "a"), tmp_path)
    t = to_frames(read_xml(DOC.encode(), "b"))["tables"]
    t.to_parquet(tmp_path / "tables.parquet", index=False)
    with pytest.raises(ValueError, match="여럿"):
        load(tmp_path)
