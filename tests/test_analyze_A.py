import math

import pytest

import analyze_A
import aplib

TAX = aplib.load_taxonomy()
Z = 1.959963984540054


def row(day, code, conf, ok, cause="", kind="分野別", first="Y", src="R6秋", n="1", solve=120, analysis=60):
    return {"日目": str(day), "種別": kind, "初見": first, "出典": src, "問番号": str(n), "コード": code,
            "確信度": conf, "正誤": ok, "原因": cause, "正解の根拠": "", "誤選択肢が違う理由": "",
            "解答秒": str(solve), "分析秒": str(analysis)}


@pytest.mark.parametrize("k, n", [(8, 10), (0, 5), (5, 5), (3, 5), (48, 80)])
def test_wilson_bounds_solve_score_equation(k, n):
    lo, hi = aplib.wilson_interval(k, n)
    for p in (lo, hi):
        assert abs(k / n - p) == pytest.approx(Z * math.sqrt(p * (1 - p) / n), abs=1e-12)
    assert lo <= k / n <= hi


def test_wilson_known_value_and_edges():
    lo, hi = aplib.wilson_interval(8, 10)
    assert (round(lo, 4), round(hi, 4)) == (0.4902, 0.9433)
    assert aplib.wilson_interval(0, 0) == (0.0, 1.0)


def test_middle_stats_and_verdicts():
    rows = [row(1, "09-3", "A", "正"), row(1, "09-3", "C", "正", "混同"), row(1, "09-4", "B", "誤", "知識不足")]
    db = {s.mid: s for s in analyze_A.middle_stats(rows, TAX)}["09"]
    assert (db.n, db.wrong) == (3, 2) and dict(db.tags) == {"09-3": 1, "09-4": 1}
    S = analyze_A.MiddleStat
    assert S("01", "", 0, 0, None).verdict == "未着手"
    assert S("01", "", 20, 15, None).verdict == "弱点"
    assert S("01", "", 40, 4, None).verdict == "合格圏"
    assert S("01", "", 5, 2, None).verdict == "保留"


def test_top_wrong_order_and_tiebreak():
    S = analyze_A.MiddleStat
    stats = [S("01", "a", 10, 3, None), S("02", "b", 5, 3, None), S("03", "c", 10, 4, None), S("05", "e", 10, 0, None)]
    assert [s.mid for s in analyze_A.top_wrong(stats)] == ["03", "02", "01"]


def test_priorities_and_allocation():
    # 技術要素 10問中5問誤答（50%）、ストラテジ 10問中2問誤答（20%）、他は未解答
    rows = [row(1, "09-3", "B", "誤" if i < 5 else "正", "混同" if i < 5 else "") for i in range(10)]
    rows += [row(1, "19-1", "B", "誤" if i < 2 else "正", "混同" if i < 2 else "") for i in range(10)]
    prios = analyze_A.priorities(rows)
    assert prios[0][0] == "技術要素" and prios[0][4] == pytest.approx(22.3 * 0.5)
    assert prios[1][0] == "ストラテジ" and prios[1][4] == pytest.approx(20.0 * 0.2)
    alloc = analyze_A.allocate(prios)
    assert sum(n for _, n in alloc) == 240 and all(n % 10 == 0 for _, n in alloc)
    # 11.15 : 4.0 → 240問を 10問単位で 180 : 60（最大剰余法）
    assert alloc == [("技術要素", 180), ("ストラテジ", 60)]
    days = analyze_A.pack_days(alloc)
    assert days[0] == (2, 80, [("技術要素", 80)])
    assert days[3] == (5, 40, [("技術要素", 20), ("ストラテジ", 20)])  # 180 = 80+40+40+20
    assert sum(n for _, _, parts in days for _, n in parts) == 240


def test_allocation_falls_back_to_exam_weights_without_errors():
    alloc = analyze_A.allocate(analyze_A.priorities([]))
    assert sum(n for _, n in alloc) == 240
    assert dict(alloc)["技術要素"] > dict(alloc)["開発技術"]


def test_report_uses_first_seen_rows_for_judgement_and_counts_plan_without_review():
    rows = [row(1, "09-3", "B", "誤", "混同", kind="通し", n=str(i)) for i in range(1, 3)]
    rows += [row(2, "09-3", "A", "正", kind="復習", first="N", n="1", solve=60, analysis=0)]   # 解き直し
    rows += [row(2, "11-1", "C", "正", "知識不足", n="9", solve=100, analysis=140)]
    plan = analyze_A.load_plan()
    rep = analyze_A.build_report(rows, TAX, plan, 2)
    assert "# 科目A 日次レポート 2日目" in rep
    assert "| 当日 | 復習 | 1 | 0 | 100.0% |" in rep and "| 当日 | 計 | 2 | 1 | 50.0% |" in rep
    assert "| 当日の問題数（技術要素：11 セキュリティ40＋09 DB・10 NW 40） | 80 | 1 | -79 |" in rep
    assert "| 累計問題数 | 160 | 3 | -157 |" in rep
    # 計画時間：80問×3.375分＋15分 = 285分 = 4.75時間。実測 (60+0+100+140)/3600 = 0.08時間
    assert "| 当日の所要時間 | 4.75時間 | 0.08時間 | -4.67時間 |" in rep
    # 中分類09は初見の2問（通し）だけで判定。復習のA正解は含めない
    assert "| 09 | データベース | 2 | 2 | 0.0% |" in rep
    assert "2〜6日目の分野別演習240問" in rep and "| 2 | 80 |" in rep


def test_report_mock_scores_pass_probability_and_gate():
    rows = []
    for exam, day, score in (("令和7年度秋期", 1, 50), ("令和7年度春期", 8, 54), ("令和6年度秋期", 9, 58)):
        rows += [row(day, "01-1", "A", "正" if i <= score else "誤", "" if i <= score else "知識不足",
                     kind="通し", src=f"{exam} AP 午前 問{i}", n=str(i)) for i in range(1, 81)]
    rep = analyze_A.build_report(rows, TAX, analyze_A.load_plan(), 9)
    assert "| 令和6年度秋期 | 9 | 58/80 |" in rep
    assert "直近2回の平均 56.0問 → 合格確率（推定）95." in rep or "直近2回の平均 56.0問 → 合格確率（推定）94." in rep
    assert "判定ゲート（9日目以降）：56問以上：計画を続ける" in rep


def test_gate_text_thresholds():
    assert analyze_A.gate_text(56).startswith("56問以上")
    assert analyze_A.gate_text(48).startswith("48〜55問")
    assert analyze_A.gate_text(47.5).startswith("48問未満")


def test_main_writes_file_and_handles_empty_log(tmp_path, capsys):
    log = tmp_path / "log_A.csv"
    aplib.append_row(log, aplib.LOG_A_COLUMNS, row(1, "09-3", "A", "正"))
    aplib.append_row(log, aplib.LOG_A_COLUMNS, row(1, "99-9", "A", "正"))
    out = tmp_path / "rep.md"
    assert analyze_A.main(["--log", str(log), "--out", str(out)]) == 0
    rep = out.read_text(encoding="utf-8")
    assert "# 科目A 日次レポート 1日目" in rep and "除外した行（1件）" in rep
    assert "警告" in capsys.readouterr().err
    assert analyze_A.main(["--log", str(tmp_path / "none.csv")]) == 0
    assert "初見で未着手の中分類（23件）" in capsys.readouterr().out
