import aplib
import tree_A

TAX = aplib.load_taxonomy()


def test_tree_has_every_node_once():
    lines = tree_A.build_tree(TAX).splitlines()
    assert lines[0] == "AP 科目A（3分野・9大分類・23中分類・96小分類）"
    body = [ln.lstrip("│├└─  ") for ln in lines[1:]]
    assert len(body) == 3 + 9 + 23 + 96
    assert body[0] == "テクノロジ（52）"
    assert "マネジメント（18）" in body and "ストラテジ（26）" in body
    assert "09-3 データ操作" in body and "23-5 標準化関連" in body


def test_tree_depth_markers():
    lines = tree_A.build_tree(TAX).splitlines()
    assert lines[1] == "├─ テクノロジ（52）"
    assert lines[2] == "│  ├─ 1 基礎理論"
    assert lines[3] == "│  │  ├─ 01 基礎理論"
    assert lines[4] == "│  │  │  ├─ 01-1 離散数学"
    assert lines[-1].endswith("└─ 23-5 標準化関連")
