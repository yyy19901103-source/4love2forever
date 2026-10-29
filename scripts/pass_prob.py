"""科目Aの合格確率を出す。

入力：種別＝通しかつ初見＝Y の通し（80問そろった回）のうち、直近2回の正答数の平均。
計算：本番の正答数を二項分布 Bin(80, 平均/80) とし、平均を標準偏差3問の正規分布でぶらす
（年度による難しさの差、推定）。10万回のシミュレーションで P(正答数≧48) を出す。
各回は、ぶらした平均 μ について P(Bin(80, μ/80) ≧ 48) を正確に計算して平均する（乱数の揺らぎを小さくするため）。

使い方:
  python scripts/pass_prob.py            # ログから計算
  python scripts/pass_prob.py --mean 52  # 平均正答数を直接与える
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import aplib

QUESTIONS = 80
PASS_LINE = 48           # 基準点60点 = 48問（1問1.25点）
DIFFICULTY_SD = 3.0      # 年度による難しさの差（推定）
TRIALS = 100_000


@lru_cache(maxsize=None)
def tail(p_milli: int, n: int = QUESTIONS, k: int = PASS_LINE) -> float:
    """P(Bin(n, p) ≧ k)。p は 1/10000 単位に丸めた整数で受け取り、計算結果を使い回す。"""
    p = p_milli / 10000
    if p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


def pass_probability(mean: float, sd: float = DIFFICULTY_SD, trials: int = TRIALS, seed: int = 0) -> float:
    rng = random.Random(seed)
    total = 0.0
    for _ in range(trials):
        mu = min(max(rng.gauss(mean, sd), 0.0), QUESTIONS)
        total += tail(round(mu / QUESTIONS * 10000))
    return total / trials


def mock_scores(rows) -> list[tuple[str, int, int]]:
    """初見の通しの回ごとに (回, 最後の日目, 正答数)。80問そろった回だけを、日目の順に返す。"""
    by_exam: dict[str, list] = defaultdict(list)
    for r in rows:
        if r["種別"] == "通し" and r["初見"] == "Y":
            by_exam[aplib.exam_key(r["出典"])].append(r)
    out = []
    for exam, rs in by_exam.items():
        if len({r["問番号"] for r in rs}) >= QUESTIONS:
            out.append((exam, max(int(r["日目"]) for r in rs), sum(r["正誤"] == "正" for r in rs)))
    return sorted(out, key=lambda t: t[1])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--mean", type=float, help="平均正答数を直接与える（ログを使わない）")
    p.add_argument("--log", type=Path, default=aplib.LOG_A_PATH)
    args = p.parse_args(argv)
    if args.mean is None:
        rows, _ = aplib.read_log_a(args.log, aplib.load_taxonomy())
        scores = mock_scores(rows)
        if not scores:
            print("初見の通し（種別＝通し・初見＝Y、80問）の記録がまだありません")
            return 1
        recent = scores[-2:]
        for exam, day, score in recent:
            print(f"{day}日目 {exam}：{score}/80問")
        args.mean = sum(s for _, _, s in recent) / len(recent)
        print(f"直近{len(recent)}回の平均：{args.mean:.1f}問")
    prob = pass_probability(args.mean)
    print(f"合格確率（推定）P(正答数≧{PASS_LINE}) = {prob:.1%}"
          f"（Bin(80, {args.mean:.1f}/80)、平均を標準偏差{DIFFICULTY_SD:.0f}問でぶらす、{TRIALS:,}回）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
