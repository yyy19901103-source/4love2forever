import aplib
import import_ipa as I
import syllabus as S


def test_exam_label_and_urls():
    assert I.exam_label("2025r07a") == "令和7年度秋期"
    assert I.exam_label("2024r06h") == "令和6年度春期"
    assert I.ap_siken_url("2025r07a", 3) == "https://www.ap-siken.com/kakomon/07_aki/q3.html"
    assert I.ipa_year_url("2022r04a") == "https://www.ipa.go.jp/shiken/mondai-kaiotu/2022r04.html"


def test_parse_answers_from_layout_text():
    text = "問番号 正解 分野\n 問1     ウ  Ｔ   問 21    ウ  Ｔ\n問 80    ア  Ｓ\n"
    assert I.parse_answers(text) == {1: ("ウ", "T"), 21: ("ウ", "T"), 80: ("ア", "S")}


def test_clean_line_fixes_ocr_errors_but_keeps_choice_labels():
    assert I.clean_line("間 19 モー ター の 軸") == "問19 モーターの軸"
    assert I.clean_line("エエ 全 デー タ の うち") == "エ 全データのうち"
    assert I.clean_line("ア 主記憶 イ 補助 記憶") == "ア 主記憶 イ 補助記憶"


def test_number_variants_handle_zero_read_as_nine():
    assert "10" in I.number_variants("19")
    assert "40" in I.number_variants("49")
    assert I.number_variants("12") == {"12"}


def test_split_questions_uses_order_when_digits_are_misread():
    pages = ["問1 最初の問題\nア a\nイ b\nウ c\nエ d\n問2 二問目\nア a イ b ウ c エ d\n",
             "問29 三問目（本当は問3、番号を読み違え）\nア a\nイ b\nウ c\nエ d\n- 3 -\n"]
    qs = I.split_questions(pages, expected=3)
    assert sorted(qs) == [1, 2, 3]
    assert qs[3]["page"] == 2 and qs[3]["lines"][0].startswith("三問目")


def test_parse_choices_line_and_inline_and_trailing_label():
    stem, ch = I.parse_choices(["本文の1行目", "本文の2行目", "ア 33 イ 50 ウ 67 エ 80"])
    assert stem == "本文の1行目本文の2行目" and ch == {"ア": "33", "イ": "50", "ウ": "67", "エ": "80"}
    _, ch = I.parse_choices(["問い", "ア 長い選択肢の", "続き", "イ 二つ目", "ウ 三つ目 エ", "四つ目"])
    assert ch == {"ア": "長い選択肢の続き", "イ": "二つ目", "ウ": "三つ目", "エ": "四つ目"}


def test_tidy_choice_removes_page_number_debris_only():
    assert I.tidy_choice("5,000ーー 7 ーー") == "5,000"
    assert I.tidy_choice("80イ ォー |」") == "80"
    assert I.tidy_choice("8 ビット") == "8 ビット"


def test_guess_code_prefers_specific_terms_within_field():
    sm = S.small_categories(S.load_syllabus())
    notes = S.load_notes()
    code, hits = I.guess_code("DBMS をシステム障害発生後に再立上げするとき, ロールフォワードすべきトランザクション", "T", sm, notes)
    assert code.startswith("09-")
    code, _ = I.guess_code("システム監査報告書の改善提案に対するフォローアップ", "M", sm, notes)
    assert code == "16-1"


def test_imported_banks_are_valid_and_complete():
    import json
    tax = aplib.load_taxonomy()
    import qbank
    files = sorted((aplib.DATA_DIR / "questions").glob("ipa_*.jsonl"))
    assert files
    qs, errors = qbank.load_questions(files, tax)
    assert errors == []
    for f in files:
        rows = [json.loads(line) for line in open(f, encoding="utf-8")]
        assert len(rows) == 80 and [r["id"][-2:] for r in rows] == [f"{n:02d}" for n in range(1, 81)]
        assert all(r["origin"] == "IPA過去問" and r["answer"] in I.LABELS and r["note"] for r in rows)
