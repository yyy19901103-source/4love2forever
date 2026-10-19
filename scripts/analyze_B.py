"""科目Bの分野別レポートと、選択分野の入れ替え判定を Markdown で出力する。

使い方: python scripts/analyze_B.py [--from B1 --to B7] [--out report.md]
日目は B1〜B26（「B3」「3」どちらの表記でも可）。
本命分野の平均得点率が6割未満なら、予備分野（6割以上が条件）と入れ替える案を出す。
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import aplib

PASS_RATE = 60.0                      # 得点率（%）の基準
MIN_PER_QUESTION = 150 / 5            # 150分で5問 → 30分/問（推定の配分）
DEFAULT_MAIN = ("プロジェクトマネジメント", "データベース", "システム監査", "経営戦略")
DEFAULT_RESERVE = ("サービスマネジメント",)
B_DAYS = 26                           # 科目Bの日程 B1〜B26


@dataclass
class FieldStat:
    field: str
    scores: list[float]
    minutes: list[float]

    @property
    def n(self) -> int:
        return len(self.scores)

    @property
    def mean_score(self) -> float | None:
        return sum(self.scores) / self.n if self.n else None

    @property
    def mean_minutes(self) -> float | None:
        return sum(self.minutes) / self.n if self.n else None


def _number(v: str) -> float | None:
    try:
        return float(v)
    except ValueError:
        return None


def parse_b_day(v: str) -> int | None:
    """「B3」「b3」「3」→ 3。範囲外や不正な値は None。"""
    v = v.strip().upper().removeprefix("B")
    return int(v) if v.isdigit() and 1 <= int(v) <= B_DAYS else None


def validate_row_b(row: dict[str, str]) -> list[str]:
    missing = [c for c in aplib.LOG_B_COLUMNS if c not in row]
    if missing:
        return [f"列が不足しています: {missing}"]
    errors = []
    if parse_b_day(row["日目"]) is None:
        errors.append(f"日目は B1〜B{B_DAYS}（または1〜{B_DAYS}）です: {row['日目']!r}")
    if not row["分野"].strip():
        errors.append("分野が空です")
    score = _number(row["得点率"])
    if score is None or not 0 <= score <= 100:
        errors.append(f"得点率は0〜100の数値（%）です: {row['得点率']!r}")
    minutes = _number(row["所要分"])
    if minutes is None or minutes <= 0:
        errors.append(f"所要分は正の数値です: {row['所要分']!r}")
    return errors


def read_log_b(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], []
    rows, warnings = [], []
    with open(path, encoding=aplib.ENCODING, newline="") as f:
        for lineno, row in enumerate(csv.DictReader(f), start=2):
            errs = validate_row_b(row)
            if errs:
                warnings.append(f"{path.name} {lineno}行目を除外: {'; '.join(errs)}")
                continue
            if row["分野"] not in aplib.B_FIELDS:
                warnings.append(f"{path.name} {lineno}行目：分野 {row['分野']!r} は既知の11分野にありません（表記ゆれの可能性。集計には含めます）")
            rows.append(row)
    return rows, warnings


def field_stats(rows) -> dict[str, FieldStat]:
    stats: dict[str, FieldStat] = {}
    for r in rows:
        s = stats.setdefault(r["分野"], FieldStat(r["分野"], [], []))
        s.scores.append(float(r["得点率"]))
        s.minutes.append(float(r["所要分"]))
    return stats


def decide_selection(stats: dict[str, FieldStat], main, reserve):
    """(判定行のリスト, 確定後の選択分野) を返す。判定行は (分野, 区分, 判定)。"""
    get = lambda f: stats.get(f, FieldStat(f, [], []))
    failing = sorted((f for f in main if get(f).n and get(f).mean_score < PASS_RATE),
                     key=lambda f: (get(f).mean_score, f))
    usable = [f for f in reserve if get(f).n and get(f).mean_score >= PASS_RATE]
    usable.sort(key=lambda f: (-get(f).mean_score, f))
    swaps = dict(zip(failing, usable))

    verdicts = []
    for f in main:
        s = get(f)
        if s.n == 0:
            verdicts.append((f, "本命", "未測定"))
        elif f in swaps:
            verdicts.append((f, "本命", f"6割未満 → {swaps[f]} と入れ替え"))
        elif f in failing:
            verdicts.append((f, "本命", "6割未満だが入れ替え先なし → 継続して補強"))
        else:
            verdicts.append((f, "本命", "継続（6割以上）"))
    for f in reserve:
        s = get(f)
        if f in swaps.values():
            verdicts.append((f, "予備", "選択に昇格"))
        elif s.n == 0:
            verdicts.append((f, "予備", "未測定"))
        elif s.mean_score < PASS_RATE:
            verdicts.append((f, "予備", "6割未満のため入れ替え先にしない"))
        else:
            verdicts.append((f, "予備", "待機（6割以上、入れ替え不要）"))
    selection = [swaps.get(f, f) for f in main]
    return verdicts, selection


def fmt(x: float | None, unit: str) -> str:
    return "—" if x is None else f"{x:.1f}{unit}"


def build_report(rows, main, reserve, warnings=(), period: str = "全期間") -> str:
    stats = field_stats(rows)
    out = []
    w = out.append
    w(f"# 科目B 分野別レポート（{period}）")
    w("")
    w("根拠区分：得点率・所要分は「実測」、本命・予備の分野は「ユーザー提示」、30分/問の配分は「推定」（150分÷5問）。")
    w("")
    w("## 1. 分野別（実測）")
    w("| 分野 | 区分 | 問題数 | 平均得点率 | 最低〜最高 | 平均所要分 | 配分30分との差 |")
    w("| --- | --- | ---: | ---: | --- | ---: | ---: |")
    role = {aplib.B_REQUIRED_FIELD: "必須", **{f: "本命" for f in main}, **{f: "予備" for f in reserve}}
    order = [aplib.B_REQUIRED_FIELD, *main, *reserve]
    order += sorted(f for f in stats if f not in order)
    for f in order:
        s = stats.get(f, FieldStat(f, [], []))
        rng = "—" if not s.n else f"{min(s.scores):.0f}〜{max(s.scores):.0f}%"
        diff = "—" if s.mean_minutes is None else f"{s.mean_minutes - MIN_PER_QUESTION:+.1f}分"
        w(f"| {f} | {role.get(f, 'その他')} | {s.n} | {fmt(s.mean_score, '%')} | {rng} | {fmt(s.mean_minutes, '分')} | {diff} |")
    w("")

    verdicts, selection = decide_selection(stats, main, reserve)
    w("## 2. 選択分野の入れ替え判定（基準：平均得点率 6割未満）")
    req = stats.get(aplib.B_REQUIRED_FIELD)
    if req and req.mean_score < PASS_RATE:
        w(f"- {aplib.B_REQUIRED_FIELD}（必須）が {req.mean_score:.1f}% で6割未満です。必須のため入れ替えできません。最優先で補強してください。")
    for f, kind, v in verdicts:
        w(f"- {f}（{kind}）：{v}")
    w("")
    w(f"判定後の選択4分野：{' / '.join(selection)}")
    thin = [f for f in [*main, *reserve] if stats.get(f) and stats[f].n == 1]
    if thin:
        w("")
        w(f"注意：{', '.join(thin)} は1問だけの結果です。1問の得点率は設問の当たり外れで大きく動くため、境界付近（50〜70%）なら2問目を解いてから確定してください。")
    if warnings:
        w("")
        w("## 3. 警告")
        for msg in warnings:
            w(f"- {msg}")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--log", type=Path, default=aplib.LOG_B_PATH)
    p.add_argument("--from", dest="start", help="集計開始の日目（両端を含む、例 B1）")
    p.add_argument("--to", dest="end", help="集計終了の日目（両端を含む、例 B7）")
    p.add_argument("--main", default=",".join(DEFAULT_MAIN), help="本命分野（カンマ区切り）")
    p.add_argument("--reserve", default=",".join(DEFAULT_RESERVE), help="予備分野（カンマ区切り）")
    p.add_argument("--out", type=Path)
    args = p.parse_args(argv)

    start = parse_b_day(args.start) if args.start else 1
    end = parse_b_day(args.end) if args.end else B_DAYS
    if start is None or end is None or start > end:
        p.error(f"--from / --to は B1〜B{B_DAYS} で、from ≦ to にしてください")
    rows, warnings = read_log_b(args.log)
    rows = [r for r in rows if start <= parse_b_day(r["日目"]) <= end]
    period = f"B{start}〜B{end}" if args.start or args.end else "全期間"
    main_fields = tuple(f.strip() for f in args.main.split(",") if f.strip())
    reserve_fields = tuple(f.strip() for f in args.reserve.split(",") if f.strip())
    report = build_report(rows, main_fields, reserve_fields, warnings, period)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"出力しました: {args.out}")
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
