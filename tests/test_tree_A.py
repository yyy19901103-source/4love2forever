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


KNOW = tree_A.load_knowledge()


def test_knowledge_covers_every_small_category():
    assert set(KNOW) == set(TAX)
    assert all(len(items) >= 2 for items in KNOW.values())
    assert sum(len(v) for v in KNOW.values()) == 433


def test_knowledge_items_are_not_split_or_duplicated():
    for code, items in KNOW.items():
        assert len(items) == len(set(items)), code
        for it in items:
            # 区切り文字の誤りで割れた項目は、かっこの対応が崩れたり1文字だけになったりする
            assert it.count("（") == it.count("）") and it.count("(") == it.count(")"), it
            assert len(it) >= 2, (code, it)
    assert "TCP/IP" in KNOW["10-3"] and "A/D・D/A変換" in KNOW["01-5"]


def test_detail_tree_shows_items_inline():
    text = tree_A.build_tree(TAX, KNOW)
    assert text.splitlines()[0].endswith("学習項目 433")
    assert "09-3 データ操作：関係代数（選択・射影・結合・和・差・直積）、" in text
    assert len(text.splitlines()) == 1 + 3 + 9 + 23 + 96
