"""AP 科目Aの知識体系（taxonomy.csv）をツリー表示する。

使い方: python scripts/tree_A.py [--out docs/taxonomy_tree.md]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import aplib


def build_tree(taxonomy) -> str:
    # 分野 → 大分類 → 中分類 → 小分類 の順に、CSV の並び（番号順）を保って入れ子にする
    tree: dict = {}
    for row in taxonomy.values():
        major = f"{row['大分類番号']} {row['大分類']}"
        mid = f"{row['中分類番号']} {row['中分類']}"
        tree.setdefault(row["分野"], {}).setdefault(major, {}).setdefault(mid, []).append(
            f"{row['コード']} {row['小分類']}")

    counts = {f: sum(len(s) for m in majors.values() for s in m.values()) for f, majors in tree.items()}
    lines = [f"AP 科目A（3分野・9大分類・23中分類・{len(taxonomy)}小分類）"]

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
    p.add_argument("--out", type=Path, help="Markdown の出力先（省略時は標準出力）")
    args = p.parse_args(argv)
    tree = build_tree(aplib.load_taxonomy(args.taxonomy))
    if args.out:
        args.out.write_text("# AP 科目A 知識体系ツリー\n\n"
                            "`python scripts/tree_A.py --out docs/taxonomy_tree.md` で data/taxonomy.csv から生成。"
                            "記録コードは「中分類2桁-小分類番号」。\n\n```text\n" + tree + "```\n", encoding="utf-8")
    else:
        sys.stdout.write(tree)
    return 0


if __name__ == "__main__":
    sys.exit(main())
