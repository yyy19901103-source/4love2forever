import csv

import pytest

import add_log
import aplib

TAX = aplib.load_taxonomy()


def run(log, answers):
    """回答リストを順に入力として与えて main を実行する。"""
    feed = iter(answers)
    out = []
    rc = add_log.main(["--log", str(log)], input_fn=lambda _p: next(feed), output_fn=out.append)
    return rc, out


def read(log):
    with open(log, encoding=aplib.ENCODING, newline="") as f:
        return list(csv.DictReader(f))


def row(**kw):
    base = {"日目": "1", "種別": "通し", "初見": "Y", "出典": "R6秋", "問番号": "1", "コード": "09-3",
            "確信度": "B", "正誤": "誤", "原因": "混同", "正解の根拠": "", "誤選択肢が違う理由": "",
            "解答秒": "100", "分析秒": "50"}
    base.update(kw)
    return base


def test_confidence_a_correct_skips_analysis(tmp_path):
    log = tmp_path / "log_A.csv"
    # 日目(既定1) 種別=1(通し) 出典 問番号 初見(既定Y) コード 確信度 正誤 解答秒 確認
    rc, out = run(log, ["", "1", "R6秋", "1", "", "09-3", "a", "o", "1:30", "y"])
    assert rc == 0
    assert read(log) == [{
        "日目": "1", "種別": "通し", "初見": "Y", "出典": "R6秋", "問番号": "1", "コード": "09-3",
        "確信度": "A", "正誤": "正", "原因": "", "正解の根拠": "", "誤選択肢が違う理由": "",
        "解答秒": "90", "分析秒": "0"}]
    assert any("分析は省きます" in line for line in out)


def test_confidence_b_correct_asks_analysis_without_cause(tmp_path):
    log = tmp_path / "log_A.csv"
    rc, _ = run(log, ["2", "2", "R5春", "12", "", "9-3", "B", "正", "100", "根拠", "理由", "200", ""])
    assert rc == 0
    r = read(log)[0]
    assert (r["日目"], r["種別"], r["コード"], r["原因"], r["正解の根拠"], r["分析秒"]) == ("2", "分野別", "09-3", "", "根拠", "200")


def test_wrong_answer_requires_cause_and_analysis(tmp_path):
    log = tmp_path / "log_A.csv"
    rc, out = run(log, ["3", "3", "R6秋", "5", "", "11-4", "C", "正", "2", "60", "根拠", "理由", "90", "y"])
    assert rc == 0
    r = read(log)[0]
    assert (r["種別"], r["原因"], r["誤選択肢が違う理由"]) == ("弱点", "混同", "理由")
    assert any("実質誤答" in line for line in out)


def test_first_seen_default_comes_from_log_and_review_is_always_n(tmp_path):
    log = tmp_path / "log_A.csv"
    aplib.append_row(log, aplib.LOG_A_COLUMNS, row(確信度="A", 正誤="正", 原因=""))
    run(log, ["2", "2", "R6秋", "1", "", "09-3", "A", "o", "60", "y"])     # 同じ問題 → 既定 N
    run(log, ["2", "4", "R6秋", "9", "", "09-3", "A", "o", "60", "y"])     # 復習 → 既定 N
    assert [r["初見"] for r in read(log)] == ["Y", "N", "N"]


def test_invalid_inputs_are_rejected_and_reasked(tmp_path):
    log = tmp_path / "log_A.csv"
    answers = [
        "18", "1",            # 日目は1〜17
        "9", "通し",          # 種別
        "", "R6秋",           # 出典が空
        "3",
        "Z", "Y",             # 初見
        "24-1", "11-4",       # コード
        "D", "b",             # 確信度
        "△", "x",             # 正誤
        "6", "知識不足",       # 原因
        "-5", "120",          # 解答秒
        "根拠", "理由", "60", "y",
    ]
    rc, out = run(log, answers)
    assert rc == 0
    r = read(log)[0]
    assert (r["日目"], r["種別"], r["初見"], r["コード"], r["確信度"], r["正誤"], r["原因"]) == \
        ("1", "通し", "Y", "11-4", "B", "誤", "知識不足")
    assert sum(line.startswith("  !") for line in out) == 9


def test_decline_or_quit_writes_nothing(tmp_path):
    log = tmp_path / "log_A.csv"
    rc, _ = run(log, ["", "1", "R6秋", "1", "", "01-1", "A", "o", "60", "n"])
    assert rc == 1 and not log.exists()
    rc, _ = run(log, ["", "q"])
    assert rc == 1 and not log.exists()


def test_append_keeps_single_header_and_bom(tmp_path):
    log = tmp_path / "log_A.csv"
    for n in ("1", "2"):
        run(log, ["", "1", "R6秋", n, "", "01-1", "A", "o", "60", "y"])
    raw = log.read_bytes()
    assert raw.count(b"\xef\xbb\xbf") == 1 and raw.startswith(b"\xef\xbb\xbf")
    assert [r["問番号"] for r in read(log)] == ["1", "2"]


@pytest.mark.parametrize("changes, message", [
    ({"日目": "0"}, "日目"),
    ({"日目": "18"}, "日目"),
    ({"種別": "本問"}, "種別"),
    ({"初見": "y"}, "初見"),
    ({"種別": "復習", "初見": "Y"}, "復習の行は初見＝N"),
    ({"コード": "99-1"}, "taxonomy"),
    ({"確信度": "D"}, "確信度"),
    ({"正誤": "○"}, "正誤"),
    ({"原因": ""}, "原因"),
    ({"正誤": "正", "確信度": "A"}, "原因を付けません"),
    ({"解答秒": "1.5"}, "解答秒"),
])
def test_validate_row_a_rejects_bad_values(changes, message):
    r = row()
    assert aplib.validate_row_a(r, TAX) == []
    r.update(changes)
    errors = aplib.validate_row_a(r, TAX)
    assert errors and any(message in e for e in errors)


def test_needs_analysis_and_keys():
    assert aplib.needs_analysis(row()) and aplib.needs_analysis(row(正誤="正", 確信度="B", 原因=""))
    assert not aplib.needs_analysis(row(正誤="正", 確信度="A", 原因=""))
    assert aplib.question_key(row()) == ("R6秋", "1")
    assert aplib.exam_key("令和7年度秋期 AP 午前 問1（原本 p.4）") == "令和7年度秋期"
    assert aplib.exam_key("R6秋") == "R6秋"
    assert aplib.field_group("09-3") == "技術要素" and aplib.field_group("17-1") == "ストラテジ"
    assert round(sum(w for _, w in aplib.FIELD_GROUPS.values()), 1) == 80.0
