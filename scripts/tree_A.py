"""AP 科目Aの知識体系（taxonomy.csv）をツリー表示する。

使い方: python scripts/tree_A.py [--detail] [--out docs/taxonomy_tree.md]
--detail を付けると、小分類ごとの学習項目（data/knowledge_items.csv）も表示する。
--points を付けると、学習項目ごとの要点を Markdown で出力する（docs/knowledge_points.md 用）。
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import aplib

KNOWLEDGE_PATH = aplib.DATA_DIR / "knowledge_items.csv"


def load_knowledge(path: Path = KNOWLEDGE_PATH) -> dict[str, list[str]]:
    """コード → 学習項目のリスト（CSV の並び順）。"""
    items: dict[str, list[str]] = {}
    with open(path, encoding=aplib.ENCODING, newline="") as f:
        for row in csv.DictReader(f):
            items.setdefault(row["コード"], []).append(row["項目"])
    return items


def load_points(path: Path = KNOWLEDGE_PATH) -> dict[str, list[tuple[str, str]]]:
    """コード → [(項目, 要点), ...]。"""
    points: dict[str, list[tuple[str, str]]] = {}
    with open(path, encoding=aplib.ENCODING, newline="") as f:
        for row in csv.DictReader(f):
            points.setdefault(row["コード"], []).append((row["項目"], row.get("要点") or ""))
    return points


def build_points(taxonomy, points) -> str:
    lines = ["# AP 科目A 学習項目と要点", "",
             "`python scripts/tree_A.py --points --out docs/knowledge_points.md` で data/knowledge_items.csv から生成。",
             "根拠区分＝推定（Claude の知識による整理。IPA シラバス Ver.7.2 との照合は未実施）。"
             "数値例はコードで検算済み。法令は改正に注意（取適法は2026-01-01施行を二次情報で確認）。", ""]
    current_mid = None
    for code, row in taxonomy.items():
        if row["中分類番号"] != current_mid:
            current_mid = row["中分類番号"]
            lines += [f"## {current_mid} {row['中分類']}（{row['分野']}）", ""]
        lines += [f"### {code} {row['小分類']}", ""]
        lines += [f"- **{item}**：{point or '（未記入）'}" for item, point in points.get(code, [])]
        lines.append("")
    return "\n".join(lines)


def build_tree(taxonomy, knowledge: dict[str, list[str]] | None = None) -> str:
    # 分野 → 大分類 → 中分類 → 小分類 の順に、CSV の並び（番号順）を保って入れ子にする
    tree: dict = {}
    for row in taxonomy.values():
        major = f"{row['大分類番号']} {row['大分類']}"
        mid = f"{row['中分類番号']} {row['中分類']}"
        small = f"{row['コード']} {row['小分類']}"
        if knowledge is not None:
            small += "：" + "、".join(knowledge.get(row["コード"], ["（未登録）"]))
        tree.setdefault(row["分野"], {}).setdefault(major, {}).setdefault(mid, []).append(small)

    counts = {f: sum(len(s) for m in majors.values() for s in m.values()) for f, majors in tree.items()}
    lines = [f"AP 科目A（3分野・9大分類・23中分類・{len(taxonomy)}小分類）"]
    if knowledge is not None:
        lines[0] += f"　学習項目 {sum(len(knowledge.get(c, [])) for c in taxonomy)}"

    def branch(items, prefix):
        for i, item in enumerate(items):
            last = i == len(items) - 1
            yield item, prefix + ("└─ " if last else "├─ "), prefix + ("   " if last else "│  ")

    for field, fp, fc in branch(list(tree), ""):
        lines.append(f"{fp}{field}（{counts[field]}）")
        for major, mp, mc in branch(list(tree[field]), fc):
            lines.append(f"{mp}{major}")
            for mid, dp, dc in branch(list(tree[field][major]), mc):
                lines.append(f"{dp}{mid}")
                for small, sp, _ in branch(tree[field][major][mid], dc):
                    lines.append(f"{sp}{small}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--taxonomy", type=Path, default=aplib.TAXONOMY_PATH)
    p.add_argument("--detail", action="store_true", help="小分類ごとの学習項目も表示する")
    p.add_argument("--points", action="store_true", help="学習項目ごとの要点を Markdown で出力する")
    p.add_argument("--out", type=Path, help="Markdown の出力先（省略時は標準出力）")
    args = p.parse_args(argv)
    if args.points:
        text = build_points(aplib.load_taxonomy(args.taxonomy), load_points())
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        return 0
    tree = build_tree(aplib.load_taxonomy(args.taxonomy), load_knowledge() if args.detail else None)
    if args.out:
        note = ("学習項目は data/knowledge_items.csv。根拠区分＝推定（Claude の知識による整理。"
                "IPA シラバス Ver.7.2 の用語例との照合は未実施）。\n\n" if args.detail else "")
        cmd = "python scripts/tree_A.py" + (" --detail" if args.detail else "") + f" --out {args.out.as_posix()}"
        args.out.write_text("# AP 科目A 知識体系ツリー\n\n"
                            f"`{cmd}` で data/taxonomy.csv から生成。記録コードは「中分類2桁-小分類番号」。\n\n"
                            + note + "```text\n" + tree + "```\n", encoding="utf-8")
    else:
        sys.stdout.write(tree)
    return 0


if __name__ == "__main__":
    sys.exit(main())
