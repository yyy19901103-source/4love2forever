"""科目Aの日次レポートを Markdown で出力する（日付ではなく「第○日目」で集計する）。

使い方: python scripts/analyze_A.py [--day N] [--out report.md]   # 既定はログの最後の日目
- 中分類の判定・誤答上位・優先度は「初見＝Y」の行だけで計算する。一度解いた問題（復習など）を含めると
  正答率が水増しされるため。問題数・時間・原因の件数はすべての行で数える。
- 判定は中分類単位。小分類はタグとしてだけ表示する（小分類あたり数問では正答率の誤差が大きすぎるため）。
- 判定ゲートと合格確率は、種別＝通しかつ初見＝Y の80問そろった回だけを使う。
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import aplib
import pass_prob

PASS_RATE = 0.6               # 科目Aの基準点 60点 = 48/80問
SOLVE_MIN_ASSUMED = 150 / 80  # 本番ペース 150分/80問 = 1.875分/問（推定の前提）
ANALYSIS_MIN_ASSUMED = 1.5    # 分析時間の前提（推定）。最大の誤差要因
REVIEW_MIN_PER_DAY = 15       # 毎日最初の15分の解き直し
DRILL_DAYS = [(2, 80), (3, 40), (4, 40), (5, 40), (6, 40)]  # 組み替えの対象（2〜6日目の分野別演習）
GATE_DAY = 9


@dataclass
class MiddleStat:
    mid: str
    name: str
    n: int
    wrong: int
    tags: Counter

    @property
    def rate(self) -> float | None:
        return (self.n - self.wrong) / self.n if self.n else None

    @property
    def ci(self) -> tuple[float, float]:
        return aplib.wilson_interval(self.n - self.wrong, self.n)

    @property
    def verdict(self) -> str:
        if self.n == 0:
            return "未着手"
        lo, hi = self.ci
        if hi < PASS_RATE:
            return "弱点"
        if lo >= PASS_RATE:
            return "合格圏"
        return "保留"


def middle_stats(rows, taxonomy) -> list[MiddleStat]:
    mids = aplib.middle_categories(taxonomy)
    stats = {m: MiddleStat(m, name, 0, 0, Counter()) for m, name in mids.items()}
    for r in rows:
        s = stats[taxonomy[r["コード"]]["中分類番号"]]
        s.n += 1
        if aplib.is_effective_wrong(r):
            s.wrong += 1
            s.tags[r["コード"]] += 1
    return list(stats.values())


def top_wrong(stats: list[MiddleStat], k: int = 3) -> list[MiddleStat]:
    """誤答数の多い順。同数なら実質正答率の低い順、さらに中分類番号順。"""
    cand = [s for s in stats if s.wrong > 0]
    return sorted(cand, key=lambda s: (-s.wrong, s.rate, s.mid))[:k]


def load_plan(path: Path = aplib.PLAN_A_PATH) -> dict[int, dict]:
    """日目 → {問題数, 種別, 内容}。"""
    if not path.exists():
        return {}
    with open(path, encoding=aplib.ENCODING, newline="") as f:
        return {int(r["日目"]): {"問題数": int(r["問題数"]), "種別": r["種別"], "内容": r["内容"]} for r in csv.DictReader(f)}


def priorities(rows) -> list[tuple[str, float, int, int, float]]:
    """6分野ごとの (分野, 平均出題数, 解答数, 実質誤答数, 優先度＝平均出題数×誤答率)。優先度の高い順。"""
    out = []
    for name, (_, weight) in aplib.FIELD_GROUPS.items():
        rs = [r for r in rows if aplib.field_group(r["コード"]) == name]
        wrong = sum(aplib.is_effective_wrong(r) for r in rs)
        rate = wrong / len(rs) if rs else 0.0
        out.append((name, weight, len(rs), wrong, weight * rate))
    return sorted(out, key=lambda t: (-t[4], -t[1]))


def allocate(prios, total: int = 240, unit: int = 10) -> list[tuple[str, int]]:
    """total 問を優先度に比例して unit 問単位で配分する（最大剰余法）。優先度がすべて0なら平均出題数に比例。"""
    weights = [p[4] for p in prios] if any(p[4] > 0 for p in prios) else [p[1] for p in prios]
    units = total // unit
    raw = [w / sum(weights) * units for w in weights]
    base = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - base[i], reverse=True)[: units - sum(base)]:
        base[i] += 1
    return [(p[0], b * unit) for p, b in zip(prios, base) if b]


def pack_days(alloc: list[tuple[str, int]], days=DRILL_DAYS) -> list[tuple[int, int, list[tuple[str, int]]]]:
    """配分を優先度の高い順に 2〜6日目へ詰める。1つの分野が2日にまたがることもある。"""
    queue = [list(a) for a in alloc]
    out = []
    for day, cap in days:
        parts, room = [], cap
        while room and queue:
            take = min(room, queue[0][1])
            parts.append((queue[0][0], take))
            queue[0][1] -= take
            room -= take
            if queue[0][1] == 0:
                queue.pop(0)
        out.append((day, cap, parts))
    return out


def pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def summary_line(rows) -> tuple[int, int, float | None]:
    n = len(rows)
    wrong = sum(aplib.is_effective_wrong(r) for r in rows)
    return n, wrong, ((n - wrong) / n if n else None)


def mean_seconds(rows, col) -> float | None:
    return sum(int(r[col]) for r in rows) / len(rows) if rows else None


def fmt_sec(x: float | None) -> str:
    return "—" if x is None else f"{x:.1f}秒（{x / 60:.2f}分）"


def tag_text(tags: Counter, taxonomy) -> str:
    return " ".join(f"{c}{taxonomy[c]['小分類']}×{n}" for c, n in sorted(tags.items(), key=lambda t: (-t[1], t[0])))


def gate_text(mean: float) -> str:
    if mean >= 56:
        return "56問以上：計画を続ける"
    if mean >= 48:
        return "48〜55問：10日目と12日目を、誤答数上位5中分類の演習に広げる"
    return "48問未満：11日目と13〜14日目の通しをやめ、弱点の中分類と既出問題の解き直しだけに絞る"


def build_report(rows, taxonomy, plan: dict[int, dict], day: int, warnings=()) -> str:
    cum = [r for r in rows if int(r["日目"]) <= day]
    today = [r for r in cum if int(r["日目"]) == day]
    first = [r for r in cum if r["初見"] == "Y"]
    stats = middle_stats(first, taxonomy)
    out: list[str] = []
    w = out.append

    w(f"# 科目A 日次レポート {day}日目")
    w("")
    w("根拠区分：ログ集計値は「実測」、計画値と平均出題数は「ユーザー提示」、時間の前提・合格確率・補正見込みは「推定」。")
    w("実質誤答＝誤答＋確信度Cの正解。実質正答率＝(解答数−実質誤答数)÷解答数。")
    w("")

    w("## 1. 概要（実測）")
    w("| 範囲 | 種別 | 解答数 | 実質誤答数 | 実質正答率 |")
    w("| --- | --- | ---: | ---: | ---: |")
    for label, rs in (("当日", today), ("累計", cum)):
        for kind in aplib.KINDS:
            sub = [r for r in rs if r["種別"] == kind]
            if sub:
                n, wr, rate = summary_line(sub)
                w(f"| {label} | {kind} | {n} | {wr} | {pct(rate)} |")
        n, wr, rate = summary_line(rs)
        w(f"| {label} | 計 | {n} | {wr} | {pct(rate)} |")
    w("")

    w("## 2. 初見の通しと合格確率")
    mocks = pass_prob.mock_scores(cum)
    if mocks:
        w("| 回 | 日目 | 正答数 |")
        w("| --- | ---: | ---: |")
        for exam, d, score in mocks:
            w(f"| {exam} | {d} | {score}/80 |")
        recent = mocks[-2:]
        mean = sum(s for *_, s in recent) / len(recent)
        prob = pass_prob.pass_probability(mean)
        w("")
        w(f"直近{len(recent)}回の平均 {mean:.1f}問 → 合格確率（推定）{prob:.1%}"
          f"（Bin(80, 平均/80)、平均を標準偏差{pass_prob.DIFFICULTY_SD:.0f}問でぶらす、{pass_prob.TRIALS:,}回）")
        if day >= GATE_DAY:
            w(f"判定ゲート（{GATE_DAY}日目以降）：{gate_text(mean)}")
    else:
        w("初見の通し（種別＝通し・初見＝Y、80問そろった回）はまだありません。")
    w("")

    w("## 3. 計画との差")
    w("問題数は解き直し（種別＝復習）を除いて数える。計画の時間は、問題数×（解答＋分析）＋解き直し15分。")
    w("")
    plan_day = plan.get(day, {}).get("問題数", 0)
    plan_cum = sum(p["問題数"] for d, p in plan.items() if d <= day)
    done_day = sum(r["種別"] != "復習" for r in today)
    done_cum = sum(r["種別"] != "復習" for r in cum)
    per_q = SOLVE_MIN_ASSUMED + ANALYSIS_MIN_ASSUMED
    plan_hours = (plan_day * per_q + REVIEW_MIN_PER_DAY) / 60
    day_hours = sum(int(r["解答秒"]) + int(r["分析秒"]) for r in today) / 3600
    w("| 項目 | 計画（ユーザー提示） | 実測 | 差（実測−計画） |")
    w("| --- | ---: | ---: | ---: |")
    w(f"| 当日の問題数（{plan.get(day, {}).get('内容', '計画なし')}） | {plan_day} | {done_day} | {done_day - plan_day:+d} |")
    w(f"| 累計問題数 | {plan_cum} | {done_cum} | {done_cum - plan_cum:+d} |")
    w(f"| 当日の所要時間 | {plan_hours:.2f}時間 | {day_hours:.2f}時間 | {day_hours - plan_hours:+.2f}時間 |")
    w("")
    w("| 1問あたり | 前提（推定） | 当日（実測） | 累計（実測） |")
    w("| --- | ---: | ---: | ---: |")
    analyzed_today = [r for r in today if aplib.needs_analysis(r)]
    analyzed_cum = [r for r in cum if aplib.needs_analysis(r)]
    w(f"| 平均解答秒 | {fmt_sec(SOLVE_MIN_ASSUMED * 60)} | {fmt_sec(mean_seconds(today, '解答秒'))} | {fmt_sec(mean_seconds(cum, '解答秒'))} |")
    w(f"| 平均分析秒（全問） | {fmt_sec(ANALYSIS_MIN_ASSUMED * 60)} | {fmt_sec(mean_seconds(today, '分析秒'))} | {fmt_sec(mean_seconds(cum, '分析秒'))} |")
    w(f"| 平均分析秒（分析した問のみ） | — | {fmt_sec(mean_seconds(analyzed_today, '分析秒'))} | {fmt_sec(mean_seconds(analyzed_cum, '分析秒'))} |")
    analysis_cum = mean_seconds(cum, "分析秒")
    remaining = max(sum(p["問題数"] for p in plan.values()) - done_cum, 0)
    w("")
    w(f"残り {remaining}問の見込み（推定）：前提どおり {remaining * per_q / 60:.1f}時間"
      + (f"、分析時間だけを累計実測 {analysis_cum / 60:.2f}分で補正すると "
         f"{remaining * (SOLVE_MIN_ASSUMED + analysis_cum / 60) / 60:.1f}時間（解き直し15分/日は別）" if analysis_cum is not None else "")
      + "。補正するのは最も不確かな分析時間だけで、解答時間は本番ペースに固定する。")
    w("")

    w("## 4. 中分類別（累計・初見のみ、判定は中分類単位）")
    w(f"判定：Wilson 95%信頼区間の上限 < {PASS_RATE:.0%} → 弱点、下限 ≥ {PASS_RATE:.0%} → 合格圏、それ以外 → 保留（データ不足）。")
    w("")
    w("| 中分類 | 名称 | 解答数 | 実質誤答数 | 実質正答率 | 95%信頼区間 | 判定 | 誤答の小分類タグ |")
    w("| --- | --- | ---: | ---: | ---: | --- | --- | --- |")
    for s in stats:
        ci = "—" if s.n == 0 else f"{pct(s.ci[0])}〜{pct(s.ci[1])}"
        w(f"| {s.mid} | {s.name} | {s.n} | {s.wrong} | {pct(s.rate)} | {ci} | {s.verdict} | {tag_text(s.tags, taxonomy)} |")
    w("")

    w("## 5. 誤答数の上位3中分類（弱点演習の範囲）")
    tops = top_wrong(stats)
    for i, s in enumerate(tops, start=1):
        w(f"{i}. {s.mid} {s.name}：実質誤答 {s.wrong}/{s.n}問（実質正答率 {pct(s.rate)}）　タグ：{tag_text(s.tags, taxonomy)}")
    if not tops:
        w("実質誤答はまだありません。")
    else:
        w("")
        w("並び順：実質誤答数の多い順 → 同数なら実質正答率の低い順 → 中分類番号順。")
    w("")

    w("## 6. 優先度（平均出題数×誤答率）と2〜6日目の組み替え案")
    prios = priorities(first)
    w("| 分野 | 平均出題数 | 解答数（初見） | 実質誤答数 | 誤答率 | 優先度 |")
    w("| --- | ---: | ---: | ---: | ---: | ---: |")
    for name, weight, n, wrong, prio in prios:
        w(f"| {name} | {weight:.1f} | {n} | {wrong} | {pct(wrong / n if n else None)} | {prio:.2f} |")
    w("")
    if any(r["種別"] == "通し" for r in first):
        w("2〜6日目の分野別演習240問を優先度に比例して10問単位で配分し、優先度の高い順に詰めた案：")
        w("")
        w("| 日目 | 問題数 | 内容 |")
        w("| ---: | ---: | --- |")
        for d, cap, parts in pack_days(allocate(prios)):
            w(f"| {d} | {cap} | {' ＋ '.join(f'{name} {n}' for name, n in parts) or '（予備）'} |")
        w("")
        w("7日目は計画どおり誤答数上位3中分類。誤答率は1回の通しだけだと誤差が大きい（1分野10問なら±30ポイント程度）ので、案は目安として使う。")
    else:
        w("組み替え案は、1日目の基準通し（種別＝通し）を記録した後に出す。")
    w("")

    w("## 7. 原因別の件数（実測）")
    w("| 原因 | 当日 | 累計 |")
    w("| --- | ---: | ---: |")
    day_c = Counter(r["原因"] for r in today if aplib.is_effective_wrong(r))
    cum_c = Counter(r["原因"] for r in cum if aplib.is_effective_wrong(r))
    for c in aplib.CAUSES:
        w(f"| {c} | {day_c[c]} | {cum_c[c]} |")
    w("")

    untouched = [s.mid for s in stats if s.n == 0]
    w("## 8. 注意")
    if untouched:
        w(f"- 初見で未着手の中分類（{len(untouched)}件）：{', '.join(untouched)}")
    if warnings:
        w(f"- 検証で除外した行（{len(warnings)}件）：")
        for msg in warnings:
            w(f"  - {msg}")
    if not untouched and not warnings:
        w("- なし")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--log", type=Path, default=aplib.LOG_A_PATH)
    p.add_argument("--taxonomy", type=Path, default=aplib.TAXONOMY_PATH)
    p.add_argument("--plan", type=Path, default=aplib.PLAN_A_PATH)
    p.add_argument("--day", type=int, help="報告する日目（既定：ログの最後の日目。ログが空なら1）")
    p.add_argument("--out", type=Path, help="Markdown の出力先（省略時は標準出力）")
    args = p.parse_args(argv)

    taxonomy = aplib.load_taxonomy(args.taxonomy)
    rows, warnings = aplib.read_log_a(args.log, taxonomy)
    day = args.day or max((int(r["日目"]) for r in rows), default=1)
    report = build_report(rows, taxonomy, load_plan(args.plan), day, warnings)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"出力しました: {args.out}")
    else:
        sys.stdout.write(report)
    for msg in warnings:
        print(f"警告: {msg}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
