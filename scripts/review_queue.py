"""その日の最初の15分で解き直す問題の一覧を出す（間隔をあけた復習）。

対象：前日（1日前）と3日前に、誤答または確信度C（実質誤答）だった問題。
除外：最後の誤答より後の解き直し（種別＝復習）で、2回続けて確信度Aの正解だった問題と、その日すでに解き直した問題。
解き直しの結果は、種別＝復習・初見＝N で記録する（add_log.py、または quiz.py --review）。

使い方: python scripts/review_queue.py [--day N]   # 既定はログの最後の日目＋1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import aplib

INTERVALS = (1, 3)  # 何日前の誤答を解き直すか
MASTERED = 2        # 復習で連続して確信度Aの正解がこの回数続いたら外す


def mastered(history: list[dict]) -> bool:
    """最後の誤答（実質誤答を含む）より後の復習で、確信度Aの正解が続けて2回あれば習得済みとみなす。"""
    last_wrong = max((i for i, r in enumerate(history) if aplib.is_effective_wrong(r)), default=-1)
    reviews = [r for r in history[last_wrong + 1:] if r["種別"] == "復習"]
    last = reviews[-MASTERED:]
    return len(last) == MASTERED and all(r["正誤"] == "正" and r["確信度"] == "A" for r in last)


def build_queue(rows: list[dict], day: int) -> list[dict]:
    """解き直す問題の一覧。ログの並び順を時間の順とみなす。"""
    history: dict[tuple, list[dict]] = {}
    for r in rows:
        history.setdefault(aplib.question_key(r), []).append(r)
    queue = []
    for key, hist in history.items():
        reasons = [f"{d}日前" for d in INTERVALS
                   if any(int(r["日目"]) == day - d and aplib.is_effective_wrong(r) for r in hist)]
        if not reasons or mastered(hist):
            continue
        if any(int(r["日目"]) == day and r["種別"] == "復習" for r in hist):
            continue
        last = hist[-1]
        queue.append({"出典": key[0], "問番号": key[1], "コード": last["コード"], "理由": "・".join(reasons),
                      "前回": f"{last['日目']}日目 {last['正誤']}（確信度{last['確信度']}）{last['原因']}".strip()})
    return sorted(queue, key=lambda q: (q["コード"], q["出典"], q["問番号"]))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--day", type=int, help="今日の日目（既定：ログの最後の日目＋1）")
    p.add_argument("--log", type=Path, default=aplib.LOG_A_PATH)
    args = p.parse_args(argv)
    taxonomy = aplib.load_taxonomy()
    rows, warnings = aplib.read_log_a(args.log, taxonomy)
    day = args.day or min(max((int(r["日目"]) for r in rows), default=0) + 1, aplib.PLAN_DAYS)
    queue = build_queue(rows, day)
    print(f"# {day}日目の解き直し（最初の15分）：{len(queue)}問")
    print("| 出典 | 問番号 | コード | 中分類 | 対象の理由 | 前回 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for q in queue:
        print(f"| {q['出典']} | {q['問番号']} | {q['コード']} | {taxonomy[q['コード']]['中分類']} | {q['理由']}の誤答 | {q['前回']} |")
    if len(queue) > 8:
        print(f"\n注意：{len(queue)}問は15分（1問約1.9分で約8問）に収まりません。コードの順に解き、残りは翌日に回してください。")
    for w in warnings:
        print(f"警告: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
