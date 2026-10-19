import json
import csv
import aplib
import quiz

def q(id, code, answer="イ", stem=""):
    return {"id": id, "origin": "自作", "source": "テスト", "code": code, "mid_no": code[:2], "mid": "中",
            "small": "小", "stem": stem or id, "keywords": "", "answer": answer, "has_figure": 0,
            "choices": {"ア": "a", "イ": "b", "ウ": "c", "エ": "d"}, "explanation": "解説", "explanation_author": "テスト",
            "links": []}


POOL = [q("M1", "09-3"), q("R1", "09-3"), q("R2", "09-3"), q("R3", "09-3"), q("R4", "09-4"), q("M2", "11-1")]


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 10  # 呼ばれるたびに10秒進む
        return self.t


def run(tmp_path, answers, mains, **kw):
    log = tmp_path / "log_A.csv"
    feed = iter(answers)
    out = []
    s = quiz.Session(POOL, [], log, input_fn=lambda _p: next(feed), output_fn=out.append,
                     clock=FakeClock(), **kw)
    s.run(mains)
    rows = list(csv.DictReader(open(log, encoding=aplib.ENCODING))) if log.exists() else []
    return rows, out


OK = ["イ", "A", ""]                       # 正解・確信A・Enterで次へ
NG = ["ア", "B", "1", "根拠", "."]           # 誤答・原因=知識不足


def test_wrong_answer_triggers_related_and_stops_after_two_correct(tmp_path):
    rows, out = run(tmp_path, NG + OK + OK + OK, [POOL[0], POOL[5]])
    # M1 誤答 → 関連 R1, R2 を連続正解で打ち切り → 次の M2。関連も同じ種別（分野別）・初見Yで記録
    assert [(r["問番号"], r["種別"], r["初見"], r["日目"]) for r in rows] == [
        ("M1", "分野別", "Y", "1"), ("R1", "分野別", "Y", "1"), ("R2", "分野別", "Y", "1"), ("M2", "分野別", "Y", "1")]
    assert rows[0]["原因"] == "知識不足" and rows[0]["誤選択肢が違う理由"] == "DB解説参照"
    assert any("2問続けて正解" in line for line in out)
    assert any("正解は イ" in line for line in out)


def test_related_max_three_and_no_nested_chain(tmp_path):
    # 関連1で誤答 → 関連2正解 → 関連3誤答（ここで最大3問）。関連の誤答から派生はしない
    rows, _ = run(tmp_path, NG + NG + OK + NG + OK, [POOL[0], POOL[5]])
    assert [r["問番号"] for r in rows] == ["M1", "R1", "R2", "R3", "M2"]


def test_confidence_c_correct_is_treated_as_unknown(tmp_path):
    rows, out = run(tmp_path, ["イ", "C", "2", "根拠", "理由"] + OK + OK, [POOL[0]])
    assert rows[0]["正誤"] == "正" and rows[0]["原因"] == "混同"
    assert [r["問番号"] for r in rows] == ["M1", "R1", "R2"]
    assert any("実質誤答" in line for line in out)


def test_quota_counts_related_questions(tmp_path):
    rows, out = run(tmp_path, NG + OK + OK, [POOL[0], POOL[5]], quota=2)
    assert [r["問番号"] for r in rows] == ["M1", "R1"]
    assert any("上限" in line for line in out)


def test_no_related_candidate_message(tmp_path):
    rows, out = run(tmp_path, NG, [POOL[5]])
    assert len(rows) == 1 and any("関連問題がバンクにありません" in line for line in out)


def test_exam_mode_defers_feedback_and_skips_related(tmp_path):
    rows, out = run(tmp_path, ["ア", "B", "イ", "A"] + ["4", "根拠", "理由"] + [""], [POOL[0], POOL[5]], kind="通し", quota=80)
    assert [(r["問番号"], r["正誤"], r["種別"]) for r in rows] == [("M1", "誤", "通し"), ("M2", "正", "通し")]
    assert rows[0]["原因"] == "読み違い"
    first_feedback = next(i for i, line in enumerate(out) if "不正解" in line)
    assert first_feedback > next(i for i, line in enumerate(out) if "通し終了" in line)


def test_times_are_measured(tmp_path):
    rows, _ = run(tmp_path, OK, [POOL[5]])
    assert int(rows[0]["解答秒"]) > 0 and rows[0]["分析秒"].isdigit()
    assert aplib.validate_row_a(rows[0], aplib.load_taxonomy()) == []


def test_quit_keeps_finished_rows(tmp_path):
    rows, out = run(tmp_path, OK + ["q"], [POOL[5], POOL[0]])
    assert [r["問番号"] for r in rows] == ["M2"] and any("中断" in line for line in out)


def test_confident_correct_skips_analysis_but_b_correct_asks(tmp_path):
    rows, _ = run(tmp_path, OK + ["イ", "B", "根拠B", "理由B"], [POOL[5], POOL[4]], related=False)
    assert (rows[0]["正解の根拠"], rows[1]["正解の根拠"], rows[1]["原因"]) == ("", "根拠B", "")
    assert all(aplib.validate_row_a(r, aplib.load_taxonomy()) == [] for r in rows)


def test_seen_question_is_not_first_and_review_kind_is_always_n(tmp_path):
    log = tmp_path / "log_A.csv"
    feed = iter(OK + OK)
    old = [{"出典": "テスト", "問番号": "M2"}]
    quiz.Session(POOL, old, log, input_fn=lambda _p: next(feed), output_fn=lambda _x: None,
                 clock=FakeClock(), day=3, kind="弱点").run([POOL[5], POOL[4]])
    rows = list(csv.DictReader(open(log, encoding=aplib.ENCODING)))
    assert [(r["問番号"], r["初見"], r["種別"], r["日目"]) for r in rows] == [("M2", "N", "弱点", "3"), ("R4", "Y", "弱点", "3")]
    feed = iter(OK)
    log2 = tmp_path / "log2.csv"
    s = quiz.Session(POOL, [], log2, input_fn=lambda _p: next(feed), output_fn=lambda _x: None,
                     clock=FakeClock(), day=4, kind="復習")
    s.run([POOL[5]])
    r = next(csv.DictReader(open(log2, encoding=aplib.ENCODING)))
    assert (r["種別"], r["初見"]) == ("復習", "N") and not s.related


def test_select_mains_filters():
    tax = aplib.load_taxonomy()
    log = [dict(出典="テスト", 問番号="M1", 種別="分野別", 初見="Y", コード="09-3", 確信度="B", 正誤="誤")]
    assert [x["id"] for x in quiz.select_mains(POOL, log, tax, mids=["09"])] == ["R1", "R2", "R3", "R4"]
    assert "M1" in [x["id"] for x in quiz.select_mains(POOL, log, tax, mids=["09"], include_seen=True)]
    # 誤答上位1中分類 = 09
    assert {x["mid_no"] for x in quiz.select_mains(POOL, log, tax, weak=1)} == {"09"}
    assert quiz.select_mains(POOL, [], tax, weak=1) == []


def test_main_end_to_end_with_seed_bank(tmp_path):
    log = tmp_path / "log.csv"
    feed = iter(["ア", "B", "1", "根拠", "."] + ["q"])
    out = []
    import shutil
    qdir = tmp_path / "questions"  # 自作問題だけの問題バンクで確かめる（IPA過去問の取り込み有無に左右されない）
    qdir.mkdir()
    for f in ("self_made.jsonl", "self_made_2.jsonl"):
        shutil.copy(aplib.DATA_DIR / "questions" / f, qdir / f)
    common = ["--log", str(log), "--db", str(tmp_path / "b.sqlite"), "--dir", str(qdir)]
    rc = quiz.main(["--day", "3", "--mid", "9"] + common,
                   input_fn=lambda _p: next(feed), output_fn=out.append, clock=FakeClock())
    assert rc == 0
    rows, warnings = aplib.read_log_a(log, aplib.load_taxonomy())
    assert not warnings and rows[0]["問番号"] == "SELF-09-2-001" and rows[0]["日目"] == "3"
    assert any("上限 40問" in line for line in out)  # plan_A.csv の3日目は40問
    # 翌日（4日目）の解き直し：3日目の誤答が出題され、種別＝復習・初見＝N で記録される
    out.clear()
    answer = next(json.loads(ln)["answer"] for ln in open(qdir / "self_made.jsonl", encoding="utf-8")
                  if json.loads(ln)["id"] == "SELF-09-2-001")
    feed = iter([answer, "A", ""])
    assert quiz.main(["--day", "4", "--review"] + common, input_fn=lambda _p: next(feed), output_fn=out.append,
                     clock=FakeClock()) == 0
    rows, _ = aplib.read_log_a(log, aplib.load_taxonomy())
    assert [(r["問番号"], r["種別"], r["初見"], r["日目"]) for r in rows][-1] == ("SELF-09-2-001", "復習", "N", "4")
    # 解き直す問題がなければ 1 を返す
    assert quiz.main(["--day", "4", "--review"] + common, output_fn=out.append) == 1


def test_drill_pool_excludes_reserved_exams(tmp_path):
    pool = [dict(q("A", "09-3"), source="令和7年度秋期 AP 午前 問1"), dict(q("B", "09-3"), source="令和4年度春期 AP 午前 問1"), q("C", "09-3")]
    assert [x["id"] for x in quiz.drill_pool(pool, ["令和7年度秋期"])] == ["B", "C"]
    f = tmp_path / "r.txt"
    f.write_text("# コメント\n令和7年度秋期\n\n", encoding="utf-8")
    assert quiz.load_reserved(f) == ["令和7年度秋期"]
    assert quiz.load_reserved(tmp_path / "none.txt") == []


def test_reserved_file_lists_six_newest_exams():
    assert quiz.load_reserved() == ["令和7年度秋期", "令和7年度春期", "令和6年度秋期", "令和6年度春期", "令和5年度秋期", "令和5年度春期"]


def test_parse_sheet():
    assert quiz.parse_sheet("イA") == ("イ", "A") and quiz.parse_sheet("2 b") == ("イ", "B") and quiz.parse_sheet("uc") == ("ウ", "C")
    for bad in ("イ", "A", "オA", ""):
        try:
            quiz.parse_sheet(bad)
            assert False, bad
        except ValueError:
            pass


def test_sheet_mode_hides_stem_and_measures_each_entry(tmp_path):
    # Enterで計時開始 → 2問を「解答＋確信度」で入力 → 答え合わせ（M1誤答の解析、M2はEnter）
    rows, out = run(tmp_path, ["", "アB", "イA", "4", "根拠", "理由", ""], [POOL[0], POOL[5]],
                    kind="通し", quota=80, sheet=True)
    assert [(r["問番号"], r["正誤"], r["確信度"], r["種別"]) for r in rows] == [("M1", "誤", "B", "通し"), ("M2", "正", "A", "通し")]
    assert not any(line == "M1" for line in out)          # 問題文（stem＝id）は表示しない
    assert all(int(r["解答秒"]) > 0 for r in rows)
    assert any("正答数 1/2" in line for line in out)
    assert not quiz.pending_path(tmp_path / "log_A.csv").exists()


def test_interrupted_grading_is_saved_and_resumed(tmp_path):
    import shutil
    qdir = tmp_path / "questions"
    qdir.mkdir()
    shutil.copy(aplib.DATA_DIR / "questions" / "self_made.jsonl", qdir / "self_made.jsonl")
    log = tmp_path / "log.csv"
    common = ["--log", str(log), "--db", str(tmp_path / "b.sqlite"), "--dir", str(qdir)]
    qs = [json.loads(ln) for ln in open(qdir / "self_made.jsonl", encoding="utf-8")]
    wrong = {"ア": "イ", "イ": "ウ", "ウ": "エ", "エ": "ア"}
    mid_qs = sorted([x for x in qs if x["code"].startswith("09-")], key=lambda x: x["id"])[:2]
    feed = iter([wrong[mid_qs[0]["answer"]] + "B", wrong[mid_qs[1]["answer"]] + "B", "q"])
    out = []
    # 通しを2問だけ解き（--count 2）、1問目の答え合わせで中断
    assert quiz.main(["--day", "1", "--mid", "9", "--exam", "--sheet", "--count", "2", "--use-reserved"] + common,
                     input_fn=lambda p: "" if "計時" in p else next(feed), output_fn=out.append, clock=FakeClock()) == 0
    pend = quiz.pending_path(log)
    assert pend.exists() and not log.exists()
    # 保留があると新しい演習は始めない
    assert quiz.main(["--day", "2", "--mid", "9"] + common, output_fn=out.append) == 1
    assert any("--resume" in line for line in out)
    feed = iter(["1", "根拠", "理由", "2", "根拠", "理由"])
    assert quiz.main(["--day", "2", "--resume"] + common, input_fn=lambda _p: next(feed), output_fn=out.append,
                     clock=FakeClock()) == 0
    rows, warnings = aplib.read_log_a(log, aplib.load_taxonomy())
    assert not warnings and [(r["問番号"], r["日目"], r["種別"], r["原因"]) for r in rows] == [
        (mid_qs[0]["id"], "1", "通し", "知識不足"), (mid_qs[1]["id"], "1", "通し", "混同")]
    assert not pend.exists()
    assert quiz.main(["--day", "2", "--resume"] + common, output_fn=out.append) == 1
