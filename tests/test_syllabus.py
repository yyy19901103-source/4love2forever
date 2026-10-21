import json

import aplib
import syllabus as S

TAX = aplib.load_taxonomy()
SYL = S.load_syllabus()
SMALL = S.small_categories(SYL)


def test_syllabus_matches_taxonomy_codes_and_names():
    assert set(SMALL) == set(TAX)
    for code, node in SMALL.items():
        name = node["name"].split(" ", 1)[1]
        # 14-2〜14-11 はシラバスでは「プロジェクトの統合」のように接頭辞が付く
        assert name == TAX[code]["小分類"] or name == "プロジェクトの" + TAX[code]["小分類"], code
    assert sum(len(n["items"]) for n in SMALL.values()) == 425


def test_match_item_both_directions():
    items = [{"name": "ソフトウェア開発手法", "terms": ["ウォーターフォールモデル", "スパイラルモデル"], "subs": []},
             {"name": "構造化手法", "terms": ["DFD"], "subs": []}]
    item, hits = S.match_item("ウォーターフォール", "ウォーターフォール 工程を順に進める", items)
    assert item["name"] == "ソフトウェア開発手法" and hits
    item, _ = S.match_item("データフロー", "DFD で流れを表す", items)
    assert item["name"] == "構造化手法"
    assert S.match_item("無関係", "まったく関係のない文", items) == (None, [])


def test_keywords_split_parentheses():
    assert S.keywords("回帰分析（単回帰分析，重回帰分析）") == ["回帰分析", "単回帰分析", "重回帰分析"]


def test_every_syllabus_item_has_a_point():
    direct = S.load_syllabus_points()
    names = {(c, it["name"]) for c, n in SMALL.items() for it in n["items"]}
    assert set(direct) <= names  # 直接補った要点はすべて実在のシラバス項目
    assert all(len(p) >= 15 for p in direct.values())
    result = S.check(SYL, S.load_notes(), direct)
    assert result["covered_items"] == result["total_items"] == 425
    assert result["uncovered"] == []


def test_book_lists_all_items_with_points():
    book = S.build_book(SYL, S.load_notes(), S.load_syllabus_points())
    assert book.count("\n#### ") == 425
    assert "（要点なし）" not in book
    # 学習項目の 09-4 ACID特性 は、シラバスでは 09-1 データベース管理システム に置かれる
    section = book.split("### 09-1 ")[1].split("### 09-2 ")[0]
    assert "**ACID特性**（学習項目 09-4 から）" in section


def test_scope_b_fields_map_to_log_fields():
    scope = json.load(open(aplib.DATA_DIR / "scope_B.json", encoding="utf-8"))
    names = [f["name"] for f in scope["fields"]]
    assert len(names) == 13
    mapped = {aplib.B_FIELD_ALIASES.get(n, n) for n in names}
    assert mapped == set(aplib.B_FIELDS)
    assert [f["name"] for f in scope["fields"] if f["choice"] == "必須"] == [aplib.B_REQUIRED_FIELD]
