import math

import pytest

import analyze_A
import aplib

TAX = aplib.load_taxonomy()
Z = 1.959963984540054


def row(d, code, conf, ok, cause="", solve=120, analysis=60):
    return {
        "日付": d, "出典": "R6秋", "問番号": "1", "コード": code, "確信度": conf,
        "正誤": ok, "原因": cause, "正解の根拠": "", "誤選択肢が違う理由": "",
        "解答秒": str(solve), "分析秒": str(analysis),
    }


@pytest.mark.parametrize("k, n", [(8, 10), (0, 5), (5, 5), (3, 5), (48, 80)])
def test_wilson_bounds_solve_score_equation(k, n):
    # Wilson 区間の端点 p は |k/n − p| = z·sqrt(p(1−p)/n) を満たす（定義からの独立検算）
    lo, hi = aplib.wilson_interval(k, n)
    for p in (lo, hi):
        assert abs(k / n - p) == pytest.approx(Z * math.sqrt(p * (1 - p) / n), abs=1e-12)
    assert lo <= k / n <= hi


def test_wilson_known_value_and_edges():
    lo, hi = aplib.wilson_interval(8, 10)
    assert (round(lo, 4), round(hi, 4)) == (0.4902, 0.9433)
    assert aplib.wilson_interval(0, 0) == (0.0, 1.0)
    assert aplib.wilson_interval(0, 5)[0] == 0.0
    assert aplib.wilson_interval(5, 5)[1] == pytest.approx(1.0)


def test_middle_stats_count_effective_wrong_and_tags():
    rows = [
        row("2026-10-19", "09-3", "A", "正"),
        row("2026-10-19", "09-3", "C", "正", "混同"),     # 実質誤答
        row("2026-10-19", "09-4", "B", "誤", "知識不足"),
        row("2026-10-19", "10-1", "A", "正"),
    ]
    stats = {s.mid: s for s in analyze_A.middle_stats(rows, TAX)}
    assert len(stats) == 23
    db = stats["09"]
    assert (db.n, db.wrong, db.rate) == (3, 2, pytest.approx(1 / 3))
    assert dict(db.tags) == {"09-3": 1, "09-4": 1}
    assert stats["10"].wrong == 0 and stats["01"].n == 0


def test_verdict_thresholds():
    S = analyze_A.MiddleStat
    assert S("01", "", 0, 0, None).verdict == "未着手"
    assert S("01", "", 20, 15, None).verdict == "弱点"     # 5/20: 上限 < 60%
    assert S("01", "", 40, 4, None).verdict == "合格圏"    # 36/40: 下限 ≥ 60%
    assert S("01", "", 5, 2, None).verdict == "保留"       # 3/5: 区間が60%をまたぐ


def test_top_wrong_order_and_tiebreak():
    S = analyze_A.MiddleStat
    stats = [S("01", "a", 10, 3, None), S("02", "b", 5, 3, None), S("03", "c", 10, 4, None),
             S("04", "d", 10, 1, None), S("05", "e", 10, 0, None)]
    assert [s.mid for s in analyze_A.top_wrong(stats)] == ["03", "02", "01"]
    assert [s.mid for s in analyze_A.top_wrong(stats[3:])] == ["04"]  # 誤答0は除外


def test_report_sections_plan_diff_and_cumulative_scope():
    rows = [
        row("2026-10-19", "09-3", "A", "正", solve=100, analysis=80),
        row("2026-10-19", "09-3", "B", "誤", "混同", solve=140, analysis=100),
        row("2026-10-20", "11-1", "C", "正", "知識不足", solve=120, analysis=120),
        row("2026-10-21", "01-1", "A", "正"),  # 報告日より後なので含めない
    ]
    plan = {"2026-10-19": 40, "2026-10-20": 40, "2026-10-21": 40}
    rep = analyze_A.build_report(rows, TAX, plan, "2026-10-20")

    assert "| 当日 | 1 | 1 | 0.0% | 0 | — |" in rep
    assert "| 累計 | 3 | 2 | 33.3% | 0 | — |" in rep
    assert "| 当日の問題数 | 40 | 1 | -39 |" in rep
    assert "| 累計問題数 | 80 | 3 | -77 |" in rep
    # 当日計画 40問 × 3.375分 = 135分 = 2.25時間、実測 (120+120)/3600 = 0.07時間
    assert "| 当日の所要時間 | 2.25時間 | 0.07時間 | -2.18時間 |" in rep
    # 累計の平均分析秒 (80+100+120)/3 = 100秒
    assert "100.0秒（1.67分）" in rep
    # 残り 120−3=117問、前提 117×3.375/60=6.58→6.6時間、補正 117×(1.875+1.6667)/60=6.906→6.9時間
    assert "= 117問" in rep and "= 6.6時間" in rep and "= 6.9時間" in rep
    assert "| 09 | データベース | 2 | 1 | 50.0% |" in rep
    assert "09-3データ操作×1" in rep
    # 誤答数は同数1件、実質正答率 11=0% < 09=50% なので 11 が先
    assert "1. 11 セキュリティ" in rep and "2. 09 データベース" in rep
    assert "| 混同 | 0 | 1 |" in rep and "| 知識不足 | 1 | 1 |" in rep
    assert "| 01 | 基礎理論 | 0 | 0 | — | — | 未着手 |" in rep


def test_main_excludes_invalid_rows_and_writes_file(tmp_path, capsys):
    log = tmp_path / "log_A.csv"
    aplib.append_row(log, aplib.LOG_A_COLUMNS, row("2026-10-19", "09-3", "A", "正"))
    aplib.append_row(log, aplib.LOG_A_COLUMNS, row("2026-10-19", "99-9", "A", "正"))
    out = tmp_path / "rep.md"
    assert analyze_A.main(["--log", str(log), "--out", str(out)]) == 0
    rep = out.read_text(encoding="utf-8")
    assert "# 科目A 日次レポート 2026-10-19" in rep  # 既定の報告日はログの最新日付
    assert "| 累計 | 1 | 0 | 100.0% | 0 | — |" in rep
    assert "除外した行（1件）" in rep and "99-9" in rep
    assert "警告" in capsys.readouterr().err


def test_main_with_empty_log(tmp_path, capsys):
    assert analyze_A.main(["--log", str(tmp_path / "none.csv"), "--date", "2026-10-19"]) == 0
    rep = capsys.readouterr().out
    assert "| 累計 | 0 | 0 | — | 0 | — |" in rep and "未着手の中分類（23件）" in rep
    assert "= 1080問" in rep  # 実際の plan_A.csv の合計


def test_related_rows_count_for_plan_but_not_for_verdict():
    rel = row("2026-10-19", "09-3", "A", "正")
    rel["種別"] = "関連"
    rows = [row("2026-10-19", "09-3", "B", "誤", "混同"), rel, dict(rel)]
    rep = analyze_A.build_report(rows, TAX, {"2026-10-19": 40}, "2026-10-19")
    assert "| 当日 | 1 | 1 | 0.0% | 2 | 100.0% |" in rep
    assert "| 累計問題数 | 40 | 3 | -37 |" in rep          # 関連も問題数に含める
    assert "| 09 | データベース | 1 | 1 | 0.0% |" in rep   # 判定は本問だけ
