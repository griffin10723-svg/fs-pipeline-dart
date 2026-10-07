"""DART 원문(`document.xml` zip)을 형식 중립 문서 모델로 읽는다 (D-014 범용 층).

0단계 원문 확인(2026-10-07)에서 정한 것:
- `xml.etree`는 쓸 수 없다. 7개 문서 전부 파싱 실패다(이스케이프 안 된 `&`·`<`, 예: `R&D`, `< 정정 전 >`).
  관대한 stdlib `html.parser`로 읽는다. 새 의존성을 들이지 않는다.
- 머리에 `encoding="utf-8"`이라고 적고 실제로는 CP949인 문서가 있다(KB금융 2015~2021). utf-8 실패 시 cp949로 읽는다.
- `&cr;`은 DART 전용 줄바꿈 표기다.
"""

import io
import re
import zipfile
from html.parser import HTMLParser

from docparse.model import Cell, Document, Paragraph, Table

_UNIT = re.compile(r"\(\s*단\s*위\s*[:：]?[^)]*\)")
_SECTION = re.compile(r"section-(\d+)")
_CELL_TAGS = {"td", "th", "te", "tu"}
_WS = re.compile(r"\s+")


def decode(raw: bytes) -> str:
    """선언과 상관없이 utf-8을 먼저 시도하고, 실패하면 cp949. 둘 다 아니면 예외."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp949")


def _clean(text: str) -> str:
    return _WS.sub(" ", text).strip()


class _Reader(HTMLParser):
    """SECTION-n·TITLE로 섹션 경로를, P를 문단으로, TABLE을 원표로 모은다. 태그는 소문자로 들어온다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.path: list[tuple[int, str]] = []  # (단계, 제목)
        self.paragraphs: list[Paragraph] = []
        self.tables: list[Table] = []
        self.order: list[Paragraph | Table] = []  # 단위 상속용 문서 순서
        self._tables: list[list[list[Cell]]] = []  # 중첩 표 스택
        self._row: list[list[Cell]] = []
        self._cell: list[tuple[list[str], dict]] = []
        self._title: list[str] | None = None
        self._para: list[str] | None = None
        self._level = 0

    def section(self) -> tuple[str, ...]:
        return tuple(t for _, t in self.path if t)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if m := _SECTION.fullmatch(tag):
            self._level = int(m.group(1))
            self.path = [p for p in self.path if p[0] < self._level] + [(self._level, "")]
        elif tag == "title" and not self._tables:
            self._title = []
        elif tag == "table":
            self._tables.append([])
            self._row.append([])
        elif tag == "tr" and self._tables:
            if self._row[-1]:  # 앞 행이 </TR> 없이 끝났다. 버리지 않고 넣는다
                self._tables[-1].append(self._row[-1])
            self._row[-1] = []
        elif tag in _CELL_TAGS and self._tables:
            self._cell.append(([], a))
        elif tag == "p" and not self._tables:
            self._para = []

    def handle_endtag(self, tag):
        if _SECTION.fullmatch(tag) and self.path:
            self.path.pop()
        elif tag == "title" and self._title is not None:
            text = _clean("".join(self._title))
            if self.path:
                self.path[-1] = (self.path[-1][0], text)
            self._title = None
        elif tag in _CELL_TAGS and self._cell:
            buf, a = self._cell.pop()
            self._row[-1].append(Cell(
                text=_clean("".join(buf)),
                rowspan=int(a.get("rowspan") or 1),
                colspan=int(a.get("colspan") or 1),
                header=tag == "th",
            ))
        elif tag == "tr" and self._tables and self._row[-1]:
            self._tables[-1].append(self._row[-1])
            self._row[-1] = []
        elif tag == "table" and self._tables:
            rows = self._tables.pop()
            if leftover := self._row.pop():  # 닫는 TR 없이 끝난 행
                rows.append(leftover)
            t = Table(section=self.section(), rows=rows, index=len(self.tables))
            self.tables.append(t)
            self.order.append(t)
        elif tag == "p" and self._para is not None:
            text = _clean("".join(self._para))
            if text:
                p = Paragraph(section=self.section(), text=text)
                self.paragraphs.append(p)
                self.order.append(p)
            self._para = None

    def handle_data(self, data):
        if self._title is not None:
            self._title.append(data)
        if self._cell:
            self._cell[-1][0].append(data)
        elif self._para is not None:
            self._para.append(data)


_NUMBER = re.compile(r"^\(?[△▲\-]?[\d,]+(\.\d+)?\)?원?$")


def _is_data_row(row: list) -> bool:
    return any(_NUMBER.match(c.text.replace(" ", "")) for c in row[1:])


def _table_unit(t: Table) -> re.Match | None:
    """표 단위 표기. 숫자가 있는 행의 첫 칸(행 머리)에 붙은 단위는 그 행 전용이라 뺀다.

    삼성전자 2024 손익 표 안의 단위 표기는 '기본주당이익 (단위 : 원)' 행 머리뿐이고 표 단위(백만원)는 표 앞에 있다.
    """
    for row in t.rows:
        for i, c in enumerate(row):
            if i == 0 and _is_data_row(row):
                continue
            if m := _UNIT.search(c.text):
                return m
    return None


def _text(x: Paragraph | Table) -> str:
    if isinstance(x, Paragraph):
        return x.text
    return " ".join(c.text for row in x.rows for c in row)


def _attach_units(order: list[Paragraph | Table]) -> None:
    """표 안의 단위 표기, 없으면 같은 섹션의 바로 앞 문단·표의 단위 표기를 붙인다.

    KB금융 2017~2022는 '(단위: 백만원)'이 재무제표 표 바로 앞의 별도 표에 있다. 바로 앞만 보고 더 거슬러 가지 않는다.
    """
    prev: Paragraph | Table | None = None
    for x in order:
        if isinstance(x, Table):
            m = _table_unit(x)
            if m is None and prev is not None and prev.section == x.section:
                m = _UNIT.search(_text(prev)) if isinstance(prev, Paragraph) else _table_unit(prev)
            x.unit_text = m.group(0) if m else None
        prev = x


def read_xml(raw: bytes, source: str) -> Document:
    """원문 XML 1개를 문서 모델로."""
    r = _Reader()
    r.feed(decode(raw).replace("&cr;", "\n"))
    r.close()
    _attach_units(r.order)
    return Document(source=source, paragraphs=r.paragraphs, tables=r.tables)


MAX_XML = 200 * 2**20  # 압축을 푼 xml 하나의 상한. 실측 최대 약 11MB (KB금융 2022)


def xml_members(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """zip 안 xml 파일들. 압축을 풀면 상한을 넘는 것이 있으면 예외(압축 폭탄 방지)."""
    out = [i for i in zf.infolist() if i.filename.lower().endswith(".xml")]
    for i in out:
        if i.file_size > MAX_XML:
            raise ValueError(f"{i.filename}: 압축 해제 {i.file_size:,}바이트가 상한 {MAX_XML:,}을 넘는다")
    return out


def read_zip(data: bytes, source: str) -> dict[str, Document]:
    """`document.xml` 응답 zip. 본문·감사보고서 등 xml마다 문서 하나 (파일명 → 문서)."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {
            i.filename.lstrip("/"): read_xml(zf.read(i), f"{source}/{i.filename.lstrip('/')}")
            for i in xml_members(zf)
        }
