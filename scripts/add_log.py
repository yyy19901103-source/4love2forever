"""科目Aの演習結果を1問ずつ対話形式で data/log_A.csv に追記する。

使い方: python scripts/add_log.py [--log PATH] [--taxonomy PATH]
各項目は入力時に検証し、不正なら再入力を求める。最後に確認してから追記する。
日目の既定値はログの最後の日目、初見の既定値は同じ出典・問番号の行がログにあるかで決める。
分析（正解の根拠・誤選択肢が違う理由・分析秒）は、誤答と確信度B/Cのときだけ尋ねる。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

import aplib

CORRECTNESS_ALIASES = {
    "正": "正", "o": "正", "○": "正", "〇": "正", "1": "正",
    "誤": "誤", "x": "誤", "×": "誤", "0": "誤",
}


class Aborted(Exception):
    """ユーザーが入力を中断した。"""


def ask(prompt: str, parse: Callable[[str], str], input_fn=input, output_fn=print) -> str:
    """有効な値が入力されるまで繰り返し尋ねる。q で中断。"""
    while True:
        raw = input_fn(prompt).strip()
        if raw.lower() == "q":
            raise Aborted
        try:
            return parse(raw)
        except ValueError as e:
            output_fn(f"  ! {e}")


def parse_day(raw: str, default: int) -> str:
    if not raw:
        return str(default)
    if raw.isdigit() and 1 <= int(raw) <= aplib.PLAN_DAYS:
        return str(int(raw))
    raise ValueError(f"1〜{aplib.PLAN_DAYS} の整数で入力してください")


def make_choice_parser(options: tuple[str, ...], default: str | None = None):
    def parse(raw: str) -> str:
        if not raw and default:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        v = raw.upper() if raw.isascii() else raw
        if v in options:
            return v
        raise ValueError(f"{' / '.join(options)} から選んでください（番号でも可）")
    return parse


def parse_required(raw: str) -> str:
    if not raw:
        raise ValueError("空にはできません")
    if "\n" in raw:
        raise ValueError("改行は使えません")
    return raw


def make_code_parser(taxonomy):
    def parse(raw: str) -> str:
        code = raw.replace("ー", "-").replace("－", "-")
        # 「9-3」のような1桁入力も受け付けて「09-3」に正規化する
        if "-" in code:
            mid, small = code.split("-", 1)
            if mid.isdigit() and small.isdigit():
                code = f"{int(mid):02d}-{int(small)}"
        if code not in taxonomy:
            raise ValueError(f"コード {raw!r} は taxonomy.csv にありません（例: 09-3）")
        return code
    return parse


def parse_confidence(raw: str) -> str:
    v = raw.upper()
    if v not in aplib.CONFIDENCE:
        raise ValueError("A（確信）/ B（半々）/ C（勘）で入力してください")
    return v


def parse_correctness(raw: str) -> str:
    v = CORRECTNESS_ALIASES.get(raw.lower())
    if v is None:
        raise ValueError("正（o/○/1）または 誤（x/×/0）で入力してください")
    return v


def parse_cause(raw: str) -> str:
    if raw.isdigit() and 1 <= int(raw) <= len(aplib.CAUSES):
        return aplib.CAUSES[int(raw) - 1]
    if raw in aplib.CAUSES:
        return raw
    raise ValueError("番号か名称で1つ選んでください")


def parse_seconds(raw: str) -> str:
    # 「1:52」のような分:秒入力も受け付ける
    if ":" in raw:
        m, _, s = raw.partition(":")
        if m.isdigit() and s.isdigit() and int(s) < 60:
            return str(int(m) * 60 + int(s))
    elif raw.isdigit():
        return str(int(raw))
    raise ValueError("0以上の整数（秒）か 分:秒 で入力してください")


def collect_row(taxonomy, input_fn=input, output_fn=print, log_rows=()) -> dict[str, str]:
    def q(prompt, parse):
        return ask(prompt, parse, input_fn, output_fn)

    last_day = max((int(r["日目"]) for r in log_rows), default=1)
    seen = {aplib.question_key(r) for r in log_rows}
    row = {}
    row["日目"] = q(f"日目 [{last_day}]: ", lambda r: parse_day(r, last_day))
    kinds = " / ".join(f"{i}={k}" for i, k in enumerate(aplib.KINDS, start=1))
    row["種別"] = q(f"種別 {kinds}: ", make_choice_parser(aplib.KINDS))
    row["出典"] = q("出典（例: R6秋）: ", parse_required)
    row["問番号"] = q("問番号: ", parse_required)
    first = "N" if row["種別"] == "復習" or aplib.question_key(row) in seen else "Y"
    row["初見"] = q(f"初見 Y/N [{first}]: ", make_choice_parser(aplib.FIRST_SEEN, first))
    row["コード"] = q("コード（中分類-小分類、例 09-3）: ", make_code_parser(taxonomy))
    t = taxonomy[row["コード"]]
    output_fn(f"  → {t['中分類']} / {t['小分類']}")
    row["確信度"] = q("確信度 A=確信 / B=半々 / C=勘: ", parse_confidence)
    row["正誤"] = q("正誤 正(o) / 誤(x): ", parse_correctness)
    row["原因"] = row["正解の根拠"] = row["誤選択肢が違う理由"] = ""
    row["分析秒"] = "0"
    if aplib.is_effective_wrong(row):
        if row["正誤"] == "正":
            output_fn("  → 確信度Cの正解は実質誤答として扱います")
        menu = " / ".join(f"{i}={c}" for i, c in enumerate(aplib.CAUSES, start=1))
        row["原因"] = q(f"原因 {menu}: ", parse_cause)
    row["解答秒"] = q("解答秒（秒 または 分:秒）: ", parse_seconds)
    if aplib.needs_analysis(row):
        row["正解の根拠"] = q("正解の根拠: ", parse_required)
        row["誤選択肢が違う理由"] = q("誤選択肢が違う理由: ", parse_required)
        row["分析秒"] = q("分析秒（秒 または 分:秒）: ", parse_seconds)
    else:
        output_fn("  → 確信度Aの正解なので分析は省きます")
    return row


def main(argv=None, input_fn=input, output_fn=print) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--log", type=Path, default=aplib.LOG_A_PATH)
    p.add_argument("--taxonomy", type=Path, default=aplib.TAXONOMY_PATH)
    args = p.parse_args(argv)

    taxonomy = aplib.load_taxonomy(args.taxonomy)
    log_rows, _ = aplib.read_log_a(args.log, taxonomy)
    output_fn("科目A ログ入力（q で中断）")
    try:
        row = collect_row(taxonomy, input_fn, output_fn, log_rows)
        errors = aplib.validate_row_a(row, taxonomy)
        if errors:  # 各項目を検証済みなので通常は起こらないが、書き込み前の最終防壁とする
            for e in errors:
                output_fn(f"  ! {e}")
            return 1
        output_fn(", ".join(f"{c}={row[c]}" for c in aplib.LOG_A_COLUMNS))
        if input_fn("この内容で追記しますか？ [Y/n]: ").strip().lower() in ("n", "no", "q"):
            output_fn("追記しませんでした")
            return 1
    except (Aborted, EOFError, KeyboardInterrupt):
        output_fn("\n中断しました（追記していません）")
        return 1
    aplib.append_row(args.log, aplib.LOG_A_COLUMNS, row)
    output_fn(f"追記しました: {args.log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
