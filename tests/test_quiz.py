import csv
from datetime import date

import aplib
import quiz

TODAY = date(2026, 10, 19)


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
                     clock=FakeClock(), today=TODAY, **kw)
    s.run(mains)
    rows = list(csv.DictReader(open(log, encoding=aplib.ENCODING))) if log.exists() else []
    return rows, out


OK = ["イ", "A", ""]                       # 正解・確信A・Enterで次へ
NG = ["ア", "B", "1", "根拠", "."]           # 誤答・原因=知識不足


def test_wrong_answer_triggers_related_and_stops_after_two_correct(tmp_path):
    rows, out = run(tmp_path, NG + OK + OK + OK, [POOL[0], POOL[5]])
    kinds = [(r["問題ID"], r["種別"]) for r in rows]
    # M1 誤答 → 関連 R1, R2 を連続正解で打ち切り → 次の本問 M2
    assert kinds == [("M1", "本問"), ("R1", "関連"), ("R2", "関連"), ("M2", "本問")]
    assert rows[0]["原因"] == "知識不足" and rows[0]["誤選択肢が違う理由"] == "DB解説参照"
    assert any("2問続けて正解" in line for line in out)
    assert any("正解は イ" in line for line in out)


def test_related_max_three_and_no_nested_chain(tmp_path):
    # 関連1で誤答 → 関連2正解 → 関連3誤答（ここで最大3問）。関連の誤答から派生はしない
    rows, _ = run(tmp_path, NG + NG + OK + NG + OK, [POOL[0], POOL[5]])
    assert [r["種別"] for r in rows] == ["本問", "関連", "関連", "関連", "本問"]
    assert [r["問題ID"] for r in rows][1:4] == ["R1", "R2", "R3"]


def test_confidence_c_correct_is_treated_as_unknown(tmp_path):
    rows, out = run(tmp_path, ["イ", "C", "2", "根拠", "理由"] + OK + OK, [POOL[0]])
    assert rows[0]["正誤"] == "正" and rows[0]["原因"] == "混同"
    assert [r["種別"] for r in rows] == ["本問", "関連", "関連"]
    assert any("実質誤答" in line for line in out)


def test_quota_counts_related_questions(tmp_path):
    rows, out = run(tmp_path, NG + OK + OK, [POOL[0], POOL[5]], quota=2)
    assert [r["問題ID"] for r in rows] == ["M1", "R1"]
    assert any("上限" in line for line in out)


def test_no_related_candidate_message(tmp_path):
    rows, out = run(tmp_path, NG, [POOL[5]])
    assert len(rows) == 1 and any("関連問題がバンクにありません" in line for line in out)


def test_exam_mode_defers_feedback_and_skips_related(tmp_path):
    rows, out = run(tmp_path, ["ア", "B", "イ", "A"] + ["4", "根拠", "理由"] + [""], [POOL[0], POOL[5]], exam=True, quota=80)
    assert [(r["問題ID"], r["正誤"], r["種別"]) for r in rows] == [("M1", "誤", "本問"), ("M2", "正", "本問")]
    assert rows[0]["原因"] == "読み違い"
    first_feedback = next(i for i, line in enumerate(out) if "不正解" in line)
    assert first_feedback > next(i for i, line in enumerate(out) if "通し終了" in line)


def test_times_are_measured(tmp_path):
    rows, _ = run(tmp_path, OK, [POOL[5]])
    assert int(rows[0]["解答秒"]) > 0 and rows[0]["分析秒"].isdigit()
    assert aplib.validate_row_a(rows[0], aplib.load_taxonomy()) == []


def test_quit_keeps_finished_rows(tmp_path):
    rows, out = run(tmp_path, OK + ["q"], [POOL[5], POOL[0]])
    assert [r["問題ID"] for r in rows] == ["M2"] and any("中断" in line for line in out)


def test_select_mains_filters():
    tax = aplib.load_taxonomy()
    log = [dict(問題ID="M1", 種別="本問", コード="09-3", 確信度="B", 正誤="誤")]
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
    rc = quiz.main(["--mid", "9", "--log", str(log), "--db", str(tmp_path / "b.sqlite"), "--dir", str(qdir)],
                   input_fn=lambda _p: next(feed), output_fn=out.append, clock=FakeClock(), today=TODAY)
    assert rc == 0
    rows, warnings = aplib.read_log_a(log, aplib.load_taxonomy())
    assert not warnings and rows[0]["問題ID"] == "SELF-09-2-001"
    assert any("上限 40問" in line for line in out)  # 10/19 の計画は40問


def test_drill_pool_excludes_reserved_exams(tmp_path):
    pool = [dict(q("A", "09-3"), source="令和7年度秋期 AP 午前 問1"), dict(q("B", "09-3"), source="令和4年度春期 AP 午前 問1"), q("C", "09-3")]
    assert [x["id"] for x in quiz.drill_pool(pool, ["令和7年度秋期"])] == ["B", "C"]
    f = tmp_path / "r.txt"
    f.write_text("# コメント\n令和7年度秋期\n\n", encoding="utf-8")
    assert quiz.load_reserved(f) == ["令和7年度秋期"]
    assert quiz.load_reserved(tmp_path / "none.txt") == []


def test_reserved_file_lists_six_newest_exams():
    assert quiz.load_reserved() == ["令和7年度秋期", "令和7年度春期", "令和6年度秋期", "令和6年度春期", "令和5年度秋期", "令和5年度春期"]
