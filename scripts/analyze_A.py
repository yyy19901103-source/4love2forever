"""科目Aの日次レポートを Markdown で出力する。

使い方: python scripts/analyze_A.py [--date YYYY-MM-DD] [--out report.md]
集計は報告日までの累計（判定用）と報告日当日の2本立て。判定は中分類単位で行い、
小分類はタグとしてだけ表示する（小分類あたり数問では正答率の誤差が大きすぎるため）。
正答率・判定・誤答上位は本問だけで計算する。関連問題（誤答直後に解く類題）は解説を読んだ直後で
正答率が高めに出るため判定から外し、問題数・時間・原因の件数には含める。
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import aplib

PASS_RATE = 0.6               # 科目Aの基準点 60点 = 48/80問
SOLVE_MIN_ASSUMED = 150 / 80  # 本番ペース 150分/80問 = 1.875分/問（推定の前提）
ANALYSIS_MIN_ASSUMED = 1.5    # 分析時間の前提（推定）。最大の誤差要因


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


def load_plan(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    with open(path, encoding=aplib.ENCODING, newline="") as f:
        return {r["日付"]: int(r["計画問題数"]) for r in csv.DictReader(f)}


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


def is_main(row) -> bool:
    return (row.get("種別") or "本問") == "本問"


def build_report(rows, taxonomy, plan: dict[str, int], report_date: str, warnings=()) -> str:
    cum = [r for r in rows if r["日付"] <= report_date]
    day = [r for r in cum if r["日付"] == report_date]
    stats = middle_stats([r for r in cum if is_main(r)], taxonomy)
    out = []
    w = out.append

    w(f"# 科目A 日次レポート {report_date}")
    w("")
    w("根拠区分：ログ集計値は「実測」、計画値は「ユーザー提示」、時間の前提と補正見込みは「推定」。")
    w("実質誤答＝誤答＋確信度Cの正解。実質正答率＝(解答数−実質誤答数)÷解答数。")
    w("")

    w("## 1. 概要（実測）")
    w("| 範囲 | 解答数（本問） | 実質誤答数 | 実質正答率 | 関連問題数 | 関連の実質正答率 |")
    w("| --- | ---: | ---: | ---: | ---: | ---: |")
    for label, rs in (("当日", day), ("累計", cum)):
        n, wr, rate = summary_line([r for r in rs if is_main(r)])
        rn, _, rrate = summary_line([r for r in rs if not is_main(r)])
        w(f"| {label} | {n} | {wr} | {pct(rate)} | {rn} | {pct(rrate)} |")
    w("")

    w("## 2. 計画との差")
    plan_cum = sum(q for d, q in plan.items() if d <= report_date)
    plan_day = plan.get(report_date, 0)
    plan_total = sum(plan.values())
    w("問題数は本問＋関連の合計で数える（関連問題も時間を使うため）。")
    w("")
    w("| 項目 | 計画（ユーザー提示） | 実測 | 差（実測−計画） |")
    w("| --- | ---: | ---: | ---: |")
    w(f"| 当日の問題数 | {plan_day} | {len(day)} | {len(day) - plan_day:+d} |")
    w(f"| 累計問題数 | {plan_cum} | {len(cum)} | {len(cum) - plan_cum:+d} |")
    per_q_plan = SOLVE_MIN_ASSUMED + ANALYSIS_MIN_ASSUMED
    day_hours = sum(int(r["解答秒"]) + int(r["分析秒"]) for r in day) / 3600
    plan_hours = plan_day * per_q_plan / 60
    w(f"| 当日の所要時間 | {plan_hours:.2f}時間 | {day_hours:.2f}時間 | {day_hours - plan_hours:+.2f}時間 |")
    w("")
    w(f"計画時間の式：当日計画問題数 {plan_day}問 ×（解答 {SOLVE_MIN_ASSUMED:.3f}分 ＋ 分析 {ANALYSIS_MIN_ASSUMED:.1f}分）÷ 60 = {plan_hours:.2f}時間。"
      "実測は当日の（解答秒＋分析秒）の合計 ÷ 3600。")
    w("")
    w("| 1問あたり | 前提（推定） | 当日（実測） | 累計（実測） |")
    w("| --- | ---: | ---: | ---: |")
    for col, assumed in (("解答秒", SOLVE_MIN_ASSUMED), ("分析秒", ANALYSIS_MIN_ASSUMED)):
        w(f"| 平均{col} | {fmt_sec(assumed * 60)} | {fmt_sec(mean_seconds(day, col))} | {fmt_sec(mean_seconds(cum, col))} |")
    w("")
    remaining = max(plan_total - len(cum), 0)
    analysis_cum = mean_seconds(cum, "分析秒")
    w("### 残り時間の見込み（推定）")
    w(f"- 科目A計画の残り問題数：{plan_total} − {len(cum)} = {remaining}問（科目A計画の範囲 {min(plan, default='—')}〜{max(plan, default='—')} にだけ適用）")
    w(f"- 前提どおり：{remaining} × {per_q_plan:.3f}分 ÷ 60 = {remaining * per_q_plan / 60:.1f}時間")
    if analysis_cum is not None:
        corrected = SOLVE_MIN_ASSUMED + analysis_cum / 60
        w(f"- 分析時間だけを累計実測 {analysis_cum / 60:.2f}分で補正：{remaining} ×（{SOLVE_MIN_ASSUMED:.3f} ＋ {analysis_cum / 60:.2f}）分 ÷ 60 = "
          f"{remaining * corrected / 60:.1f}時間")
        w("  - 補正するのは最も不確かな分析時間だけ。解答時間は本番ペース（150分/80問）を目標値として固定する。")
    else:
        w("- 実測がないため補正できません。初日の分析秒で補正してください。")
    w("")

    w("## 3. 中分類別（累計・本問のみ、判定は中分類単位）")
    w(f"判定：Wilson 95%信頼区間の上限 < {PASS_RATE:.0%} → 弱点、下限 ≥ {PASS_RATE:.0%} → 合格圏、それ以外 → 保留（データ不足）。")
    w("")
    w("| 中分類 | 名称 | 解答数 | 実質誤答数 | 実質正答率 | 95%信頼区間 | 判定 | 誤答の小分類タグ |")
    w("| --- | --- | ---: | ---: | ---: | --- | --- | --- |")
    for s in stats:
        ci = "—" if s.n == 0 else f"{pct(s.ci[0])}〜{pct(s.ci[1])}"
        w(f"| {s.mid} | {s.name} | {s.n} | {s.wrong} | {pct(s.rate)} | {ci} | {s.verdict} | {tag_text(s.tags, taxonomy)} |")
    w("")

    w("## 4. 誤答数の上位3中分類（翌日の最初の30分で解く範囲）")
    tops = top_wrong(stats)
    if tops:
        for i, s in enumerate(tops, start=1):
            w(f"{i}. {s.mid} {s.name}：実質誤答 {s.wrong}/{s.n}問（実質正答率 {pct(s.rate)}）　タグ：{tag_text(s.tags, taxonomy)}")
        w("")
        w("並び順：実質誤答数の多い順 → 同数なら実質正答率の低い順 → 中分類番号順。")
    else:
        w("実質誤答はまだありません。")
    w("")

    w("## 5. 原因別の件数（実測）")
    w("| 原因 | 当日 | 累計 |")
    w("| --- | ---: | ---: |")
    day_c = Counter(r["原因"] for r in day if aplib.is_effective_wrong(r))
    cum_c = Counter(r["原因"] for r in cum if aplib.is_effective_wrong(r))
    for c in aplib.CAUSES:
        w(f"| {c} | {day_c[c]} | {cum_c[c]} |")
    w("")

    untouched = [s.mid for s in stats if s.n == 0]
    w("## 6. 注意")
    if untouched:
        w(f"- 未着手の中分類（{len(untouched)}件）：{', '.join(untouched)}")
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
    p.add_argument("--date", help="報告日（既定：ログの最新日付。ログが空なら今日）")
    p.add_argument("--out", type=Path, help="Markdown の出力先（省略時は標準出力）")
    args = p.parse_args(argv)

    taxonomy = aplib.load_taxonomy(args.taxonomy)
    rows, warnings = aplib.read_log_a(args.log, taxonomy)
    report_date = args.date or max((r["日付"] for r in rows), default=date.today().isoformat())
    date.fromisoformat(report_date)
    report = build_report(rows, taxonomy, load_plan(args.plan), report_date, warnings)
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
