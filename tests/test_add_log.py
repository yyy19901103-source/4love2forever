import csv
from datetime import date

import pytest

import add_log
import aplib

TAX = aplib.load_taxonomy()
TODAY = date(2026, 10, 19)


def run(tmp_path, answers):
    """回答リストを順に入力として与えて main を実行する。"""
    log = tmp_path / "log_A.csv"
    feed = iter(answers)
    out = []
    rc = add_log.main(["--log", str(log)], input_fn=lambda _p: next(feed), output_fn=out.append, today=TODAY)
    return rc, log, out


def read(log):
    with open(log, encoding=aplib.ENCODING, newline="") as f:
        return list(csv.DictReader(f))


def test_correct_answer_with_confidence_a_skips_cause(tmp_path):
    rc, log, _ = run(tmp_path, ["", "R6秋", "1", "09-3", "a", "o", "根拠", "理由", "1:30", "90", "y"])
    assert rc == 0
    rows = read(log)
    assert rows == [{
        "日付": "2026-10-19", "出典": "R6秋", "問番号": "1", "コード": "09-3", "確信度": "A",
        "正誤": "正", "原因": "", "正解の根拠": "根拠", "誤選択肢が違う理由": "理由",
        "解答秒": "90", "分析秒": "90", "問題ID": "", "種別": "本問",
    }]
    assert not aplib.read_log_a(log, TAX)[1]


def test_correct_with_confidence_c_requires_cause(tmp_path):
    rc, log, out = run(tmp_path, ["2026-10-20", "R5春", "12", "9-3", "C", "正", "2", "根拠", "理由", "100", "200", ""])
    assert rc == 0
    row = read(log)[0]
    assert row["コード"] == "09-3"  # 1桁の中分類を正規化
    assert row["原因"] == "混同"
    assert any("実質誤答" in line for line in out)


def test_invalid_inputs_are_rejected_and_reasked(tmp_path):
    answers = [
        "2026/10/19", "2026-10-19",  # 日付形式
        "", "R6秋",                  # 出典が空
        "3",
        "24-1", "09-9", "11-4",      # 存在しないコード
        "D", "b",                    # 確信度
        "△", "x",                    # 正誤
        "6", "思い違い", "知識不足",    # 原因
        "根拠", "理由",
        "-5", "1:75", "120",         # 秒
        "60", "y",
    ]
    rc, log, out = run(tmp_path, answers)
    assert rc == 0
    row = read(log)[0]
    assert (row["コード"], row["確信度"], row["正誤"], row["原因"], row["解答秒"]) == ("11-4", "B", "誤", "知識不足", "120")
    assert sum(line.startswith("  !") for line in out) == 10


def test_appends_without_duplicate_header_or_bom(tmp_path):
    for q in ("1", "2"):
        rc, log, _ = run(tmp_path, ["", "R6秋", q, "01-1", "A", "o", "根拠", "理由", "60", "30", "y"])
        assert rc == 0
    raw = log.read_bytes()
    assert raw.count(b"\xef\xbb\xbf") == 1 and raw.startswith(b"\xef\xbb\xbf")
    assert [r["問番号"] for r in read(log)] == ["1", "2"]


def test_decline_or_quit_writes_nothing(tmp_path):
    rc, log, _ = run(tmp_path, ["", "R6秋", "1", "01-1", "A", "o", "根拠", "理由", "60", "30", "n"])
    assert rc == 1 and not log.exists()
    rc, log, _ = run(tmp_path, ["", "q"])
    assert rc == 1 and not log.exists()


@pytest.mark.parametrize("changes, message", [
    ({"コード": "99-1"}, "taxonomy"),
    ({"確信度": "D"}, "確信度"),
    ({"正誤": "○"}, "正誤"),
    ({"原因": ""}, "原因"),                       # 誤答なのに原因なし
    ({"正誤": "正", "確信度": "A"}, "原因を付けません"),  # 正解なのに原因あり
    ({"解答秒": "1.5"}, "解答秒"),
    ({"日付": "10/19"}, "日付"),
    ({"種別": "復習"}, "種別"),
])
def test_validate_row_a_rejects_bad_values(changes, message):
    row = {
        "日付": "2026-10-19", "出典": "R6秋", "問番号": "1", "コード": "09-3", "確信度": "B",
        "正誤": "誤", "原因": "混同", "正解の根拠": "", "誤選択肢が違う理由": "",
        "解答秒": "100", "分析秒": "50",
    }
    assert aplib.validate_row_a(row, TAX) == []
    row.update(changes)
    errors = aplib.validate_row_a(row, TAX)
    assert errors and any(message in e for e in errors)


def test_old_log_without_optional_columns_is_read_as_main(tmp_path):
    log = tmp_path / "old.csv"
    log.write_text("日付,出典,問番号,コード,確信度,正誤,原因,正解の根拠,誤選択肢が違う理由,解答秒,分析秒\n"
                   "2026-10-19,R6秋,1,09-3,A,正,,,,60,30\n", encoding="utf-8")
    rows, warnings = aplib.read_log_a(log, TAX)
    assert not warnings and rows[0]["種別"] == "本問" and rows[0]["問題ID"] == ""
