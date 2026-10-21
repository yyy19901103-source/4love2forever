from datetime import date
from pathlib import Path

ERROR_LOG = Path(__file__).resolve().parent.parent / "docs" / "error_log.md"


def tables(text):
    """Markdown の表を（ヘッダ, 行のリスト）の一覧で返す。"""
    result, current = [], None
    for line in text.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if current is None:
                current = (cells, [])
                result.append(current)
            elif not all(set(c) <= set("-: ") for c in cells):
                current[1].append(cells)
        else:
            current = None
    return result


def test_error_log_tables_are_well_formed():
    found = tables(ERROR_LOG.read_text(encoding="utf-8"))
    assert found[0][0] == ["日付", "対象", "誤りの内容", "原因", "訂正内容", "再発防止"]
    for header, rows in found:
        assert header[0] == "日付"
        for cells in rows:
            assert len(cells) == len(header), cells
            assert all(cells), cells
            date.fromisoformat(cells[0])
