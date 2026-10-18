import analyze_B
import aplib

MAIN = analyze_B.DEFAULT_MAIN
RESERVE = analyze_B.DEFAULT_RESERVE


def row(d, field, score, minutes):
    return {"日付": d, "出典": "R6秋", "問番号": "2", "分野": field, "得点率": str(score),
            "所要分": str(minutes), "失点した設問": "", "原因": "", "書けなかった根拠の位置": ""}


def write_log(path, rows):
    for r in rows:
        aplib.append_row(path, aplib.LOG_B_COLUMNS, r)


def test_field_stats_mean_score_and_minutes():
    rows = [row("2026-11-10", "データベース", 50, 35), row("2026-11-11", "データベース", 70, 25)]
    s = analyze_B.field_stats(rows)["データベース"]
    assert (s.n, s.mean_score, s.mean_minutes) == (2, 60.0, 30.0)


def test_failing_main_is_swapped_with_reserve_at_or_above_60():
    stats = analyze_B.field_stats([
        row("2026-11-10", "プロジェクトマネジメント", 75, 28),
        row("2026-11-11", "データベース", 65, 30),
        row("2026-11-12", "システム監査", 55, 30),   # 6割未満
        row("2026-11-13", "経営戦略", 60, 30),       # ちょうど6割は継続
        row("2026-11-14", "サービスマネジメント", 60, 27),
    ])
    verdicts, selection = analyze_B.decide_selection(stats, MAIN, RESERVE)
    assert selection == ["プロジェクトマネジメント", "データベース", "サービスマネジメント", "経営戦略"]
    assert ("システム監査", "本命", "6割未満 → サービスマネジメント と入れ替え") in verdicts
    assert ("経営戦略", "本命", "継続（6割以上）") in verdicts
    assert ("サービスマネジメント", "予備", "選択に昇格") in verdicts


def test_lowest_failing_main_gets_the_only_reserve():
    stats = analyze_B.field_stats([
        row("2026-11-10", "データベース", 50, 30),
        row("2026-11-11", "経営戦略", 40, 30),
        row("2026-11-12", "サービスマネジメント", 80, 30),
    ])
    verdicts, selection = analyze_B.decide_selection(stats, MAIN, RESERVE)
    assert selection[MAIN.index("経営戦略")] == "サービスマネジメント"
    assert selection[MAIN.index("データベース")] == "データベース"
    assert ("データベース", "本命", "6割未満だが入れ替え先なし → 継続して補強") in verdicts
    assert ("プロジェクトマネジメント", "本命", "未測定") in verdicts


def test_reserve_below_60_or_unmeasured_is_not_used():
    for extra in ([row("2026-11-12", "サービスマネジメント", 55, 30)], []):
        stats = analyze_B.field_stats([row("2026-11-10", "データベース", 30, 30), *extra])
        verdicts, selection = analyze_B.decide_selection(stats, MAIN, RESERVE)
        assert selection == list(MAIN)
    assert ("サービスマネジメント", "予備", "未測定") in verdicts


def test_report_shows_required_warning_time_diff_and_single_sample_note():
    rows = [row("2026-11-10", "情報セキュリティ", 50, 35), row("2026-11-11", "データベース", 70, 33)]
    rep = analyze_B.build_report(rows, MAIN, RESERVE)
    assert "| 情報セキュリティ | 必須 | 1 | 50.0% | 50〜50% | 35.0分 | +5.0分 |" in rep
    assert "| データベース | 本命 | 1 | 70.0% | 70〜70% | 33.0分 | +3.0分 |" in rep
    assert "必須のため入れ替えできません" in rep
    assert "データベース は1問だけの結果" in rep


def test_main_filters_period_and_handles_bad_rows(tmp_path, capsys):
    log = tmp_path / "log_B.csv"
    write_log(log, [
        row("2026-11-09", "データベース", 10, 30),   # 期間外
        row("2026-11-10", "データベース", 80, 30),
        row("2026-11-11", "DB", 70, 30),             # 未知の分野名 → 警告のみ
        row("2026-11-12", "システム監査", 120, 30),   # 得点率が範囲外 → 除外
        row("2026-11-13", "経営戦略", 60, 0),         # 所要分が0 → 除外
    ])
    assert analyze_B.main(["--log", str(log), "--since", "2026-11-10", "--until", "2026-11-16"]) == 0
    rep = capsys.readouterr().out
    assert "（2026-11-10〜2026-11-16）" in rep
    assert "| データベース | 本命 | 1 | 80.0% |" in rep
    assert "| DB | その他 | 1 | 70.0% |" in rep
    assert "既知の11分野にありません" in rep
    assert rep.count("行目を除外") == 2


def test_main_with_empty_log(tmp_path, capsys):
    assert analyze_B.main(["--log", str(tmp_path / "none.csv")]) == 0
    rep = capsys.readouterr().out
    assert "判定後の選択4分野：プロジェクトマネジメント / データベース / システム監査 / 経営戦略" in rep
