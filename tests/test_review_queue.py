import aplib
import review_queue as RQ


def r(day, n, ok=False, conf="B", kind="分野別", first="Y", src="R6秋", code="09-3"):
    return {"日目": str(day), "種別": kind, "初見": first, "出典": src, "問番号": str(n), "コード": code,
            "確信度": conf, "正誤": "正" if ok else "誤", "原因": "" if ok and conf != "C" else "混同",
            "正解の根拠": "", "誤選択肢が違う理由": "", "解答秒": "60", "分析秒": "0"}


def keys(queue):
    return [(q["出典"], q["問番号"]) for q in queue]


def test_targets_wrong_or_c_from_one_and_three_days_ago():
    rows = [r(4, 1), r(4, 2, ok=True, conf="C"), r(4, 3, ok=True, conf="A"),   # 4日目：誤答・実質誤答・正解
            r(2, 4), r(3, 5)]                                                  # 2日目（3日前）と3日目（2日前）
    q = RQ.build_queue(rows, day=5)
    assert keys(q) == [("R6秋", "1"), ("R6秋", "2"), ("R6秋", "4")]
    assert q[2]["理由"] == "3日前"


def test_mastered_after_two_consecutive_confident_correct_reviews():
    base = [r(1, 1)]
    reviewed = base + [r(2, 1, ok=True, conf="A", kind="復習", first="N"), r(4, 1, ok=True, conf="A", kind="復習", first="N")]
    assert keys(RQ.build_queue(base, day=4)) == [("R6秋", "1")]
    assert RQ.mastered(reviewed)
    # 習得後に分野別でまた間違えたら、新しい誤答として対象に戻る
    assert keys(RQ.build_queue(reviewed + [r(4, 1, kind="分野別")], day=5)) == [("R6秋", "1")]
    # 復習が「A正解→誤答」なら外れない
    mixed = base + [r(2, 1, ok=True, conf="A", kind="復習", first="N"), r(4, 1, kind="復習", first="N")]
    assert keys(RQ.build_queue(mixed, day=5)) == [("R6秋", "1")]


def test_already_reviewed_today_is_skipped():
    rows = [r(3, 1), r(4, 1, ok=True, conf="B", kind="復習", first="N")]
    assert RQ.build_queue(rows, day=4) == []


def test_main_prints_table_and_default_day(tmp_path, capsys):
    log = tmp_path / "log.csv"
    for row in [r(1, 1), r(1, 2, ok=True, conf="A")]:
        aplib.append_row(log, aplib.LOG_A_COLUMNS, row)
    assert RQ.main(["--log", str(log)]) == 0
    out = capsys.readouterr().out
    assert "# 2日目の解き直し（最初の15分）：1問" in out and "| R6秋 | 1 | 09-3 | データベース | 1日前の誤答 |" in out
