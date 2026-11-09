import pytest

import pass_prob


@pytest.mark.parametrize("mean, expected", [(48, 0.54), (52, 0.81), (56, 0.95)])
def test_pass_probability_matches_claude_md(mean, expected):
    assert pass_prob.pass_probability(mean) == pytest.approx(expected, abs=0.02)


def test_tail_edges():
    assert pass_prob.tail(0) == 0.0 and pass_prob.tail(10000) == 1.0
    assert pass_prob.tail(6000) == pytest.approx(0.545, abs=0.005)  # Bin(80, 0.6) ≧ 48


def row(day, exam, n, ok, kind="通し", first="Y"):
    return {"日目": str(day), "種別": kind, "初見": first, "出典": f"{exam} AP 午前 問{n}", "問番号": str(n), "正誤": "正" if ok else "誤"}


def test_mock_scores_uses_only_complete_unseen_mocks():
    rows = [row(1, "令和7年度秋期", n, n <= 50) for n in range(1, 81)]
    rows += [row(8, "令和7年度春期", n, n <= 56) for n in range(1, 81)]
    rows += [row(9, "令和6年度秋期", n, True) for n in range(1, 41)]                   # 40問だけ → 使わない
    rows += [row(10, "令和7年度秋期", n, True, kind="復習", first="N") for n in range(1, 81)]  # 復習 → 使わない
    assert pass_prob.mock_scores(rows) == [("令和7年度秋期", 1, 50), ("令和7年度春期", 8, 56)]


def test_main_with_mean_and_empty_log(tmp_path, capsys):
    assert pass_prob.main(["--mean", "56"]) == 0
    assert "95" in capsys.readouterr().out
    assert pass_prob.main(["--log", str(tmp_path / "none.csv")]) == 1
