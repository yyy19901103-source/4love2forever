import re
from collections import Counter

import aplib

TAX = aplib.load_taxonomy()


def test_total_small_categories_is_96():
    assert len(TAX) == 96


def test_small_categories_per_field():
    counts = Counter(row["分野"] for row in TAX.values())
    assert counts == {"テクノロジ": 52, "マネジメント": 18, "ストラテジ": 26}


def test_middle_categories_are_01_to_23():
    mids = aplib.middle_categories(TAX)
    assert len(mids) == 23
    assert list(mids) == [f"{i:02d}" for i in range(1, 24)]


def test_nine_major_categories_and_three_fields():
    assert {row["大分類番号"] for row in TAX.values()} == {str(i) for i in range(1, 10)}
    assert {row["分野"] for row in TAX.values()} == {"テクノロジ", "マネジメント", "ストラテジ"}


def test_code_format_and_consistency():
    for code, row in TAX.items():
        assert re.fullmatch(r"\d{2}-\d{1,2}", code)
        assert code == f"{row['中分類番号']}-{row['小分類番号']}"
        assert row["小分類"]


def test_small_numbers_are_contiguous_within_each_middle():
    by_mid = {}
    for row in TAX.values():
        by_mid.setdefault(row["中分類番号"], []).append(int(row["小分類番号"]))
    for mid, nums in by_mid.items():
        assert sorted(nums) == list(range(1, len(nums) + 1)), mid


def test_known_examples():
    assert TAX["09-3"]["小分類"] == "データ操作"
    assert TAX["14-11"]["小分類"] == "コミュニケーション"
    assert TAX["07-2"]["小分類"] == "UX/UIデザイン"
    assert TAX["16-2"]["中分類"] == "システム監査"
