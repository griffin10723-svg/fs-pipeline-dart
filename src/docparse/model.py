"""형식 중립 문서 모델: 섹션 경로 · 문단 · 표. 리더(DART XML 등)가 이 모양으로 낸다 (D-014)."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Cell:
    """원표 셀 하나. 병합 정보는 원본 그대로 둔다."""

    text: str
    rowspan: int = 1
    colspan: int = 1
    header: bool = False


@dataclass
class Paragraph:
    section: tuple[str, ...]
    text: str


@dataclass
class Table:
    """원표. unit_text는 표 앞뒤에서 찾은 '(단위 : …)' 원문이고, 해석은 units.parse_unit이 한다."""

    section: tuple[str, ...]
    rows: list[list[Cell]]
    unit_text: str | None = None
    index: int = 0  # 문서 안 표 순번 (같은 섹션에 표가 여럿일 때 구분)

    def grid(self) -> list[list[str]]:
        return expand_spans(self.rows)


@dataclass
class Document:
    source: str  # 예: DART 접수번호
    paragraphs: list[Paragraph] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)


class SpanError(ValueError):
    """병합 셀을 펼치면 행 길이가 맞지 않는다."""


def expand_spans(rows: list[list[Cell]]) -> list[list[str]]:
    """rowspan·colspan을 펼쳐 직사각형 격자로. 병합된 칸은 같은 글자를 반복한다.

    펼친 뒤 행 길이가 다르면 원표가 깨졌거나 해석이 틀린 것이므로 예외.
    """
    grid: list[list[str | None]] = []
    for r, row in enumerate(rows):
        while len(grid) <= r:
            grid.append([])
        c = 0
        for cell in row:
            # 위 행의 rowspan이 차지한 칸은 건너뛴다
            while c < len(grid[r]) and grid[r][c] is not None:
                c += 1
            for dr in range(cell.rowspan):
                while len(grid) <= r + dr:
                    grid.append([])
                line = grid[r + dr]
                for dc in range(cell.colspan):
                    while len(line) <= c + dc:
                        line.append(None)
                    if line[c + dc] is not None:
                        raise SpanError(f"{r + dr}행 {c + dc}열이 두 셀에 겹친다")
                    line[c + dc] = cell.text
            c += cell.colspan
    widths = {len(line) for line in grid}
    if len(widths) > 1 or any(v is None for line in grid for v in line):
        raise SpanError(f"펼친 격자가 직사각형이 아니다: 행 길이 {sorted(widths)}")
    return [list(line) for line in grid]  # type: ignore[arg-type]
