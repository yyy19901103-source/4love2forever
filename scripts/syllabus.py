"""AP シラバス（data/syllabus_A.json）と学習項目（data/knowledge_items.csv）の照合。

data/syllabus_A.json はユーザー提示のファイルで、シラバス Ver.7.2 の
分野→大分類→中分類→小分類→項目→用語例 を抽出したもの。

使い方:
  python scripts/syllabus.py tree [--terms]   # シラバスの項目レベルのツリー（--terms で用語例も）
  python scripts/syllabus.py check [--out docs/syllabus_check.md]  # 学習項目との照合レポート
  python scripts/syllabus.py book [--out docs/ap_syllabus_book.md]  # シラバスの並びで要点をまとめた学習ノート

要点は2つのファイルから集める：data/knowledge_items.csv（学習項目ごと。照合でシラバス項目に対応付ける）と
data/syllabus_points.csv（学習項目が触れていなかったシラバス項目に直接付けた要点）。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

import aplib

SYLLABUS_PATH = aplib.DATA_DIR / "syllabus_A.json"
KNOWLEDGE_PATH = aplib.DATA_DIR / "knowledge_items.csv"
SYLLABUS_POINTS_PATH = aplib.DATA_DIR / "syllabus_points.csv"


def load_syllabus(path: Path = SYLLABUS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def small_categories(syllabus: dict) -> dict[str, dict]:
    """コード（例 09-3）→ 小分類ノード。"""
    out = {}
    for field in syllabus["children"]:
        for major in field["children"]:
            for mid in major["children"]:
                for small in mid["children"]:
                    out[small["code"]] = small
    return out


def item_terms(item: dict) -> list[str]:
    """項目の用語例（下位の細目名とその用語例を含む）。"""
    terms = list(item.get("terms", []))
    for sub in item.get("subs", []):
        terms.append(sub["name"])
        terms.extend(item_terms(sub))
    return terms


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[\s・，,、。()（）/]", "", t)


def keywords(text: str) -> list[str]:
    """用語を照合用の語に分ける。「回帰分析（単回帰分析，重回帰分析）」なら外と中の語を両方使う。"""
    t = unicodedata.normalize("NFKC", text)
    parts = re.split(r"[()（）,，、:：]", t)
    return [norm(p) for p in parts if len(norm(p)) >= 2]


def match_item(note_name: str, note_text: str, items: list[dict]) -> tuple[dict | None, list[str]]:
    """学習項目に最も多く一致するシラバス項目と、一致した語を返す。

    一致の条件は次のどちらか：シラバスの用語が学習項目の名前・要点に現れる、
    または学習項目の名前の語（3文字以上）がシラバスの用語の中に現れる（「ウォーターフォール」⊂「ウォーターフォールモデル」）。
    """
    text = norm(note_text)
    own = [k for k in keywords(note_name) if len(k) >= 3]
    best, best_hits = None, []
    for item in items:
        hits = set()
        for term in [item["name"], *item_terms(item)]:
            for k in keywords(term):
                if k in text or any(o in k for o in own):
                    hits.add(k)
        if len(hits) > len(best_hits):
            best, best_hits = item, sorted(hits)
    return best, best_hits


def load_notes(path: Path = KNOWLEDGE_PATH) -> dict[str, list[tuple[str, str]]]:
    notes: dict[str, list[tuple[str, str]]] = {}
    with open(path, encoding=aplib.ENCODING, newline="") as f:
        for row in csv.DictReader(f):
            notes.setdefault(row["コード"], []).append((row["項目"], row.get("要点") or ""))
    return notes


def load_syllabus_points(path: Path = SYLLABUS_POINTS_PATH) -> dict[tuple[str, str], str]:
    """(コード, シラバス項目) → 要点。"""
    if not path.exists():
        return {}
    with open(path, encoding=aplib.ENCODING, newline="") as f:
        return {(r["コード"], r["シラバス項目"]): r["要点"] for r in csv.DictReader(f)}


def check(syllabus: dict, notes: dict[str, list[tuple[str, str]]], direct: dict | None = None) -> dict:
    """照合結果。学習項目ごとに、同じ小分類で対応するシラバス項目を探し、なければ全小分類から探す。"""
    smalls = small_categories(syllabus)
    all_items = [(code, it) for code, s in smalls.items() for it in s["items"]]
    note_rows, covered = [], set()
    for code, small in smalls.items():
        for name, point in notes.get(code, []):
            item, hits = match_item(name, name + " " + point, small["items"])
            where = code
            if not item:  # 同じ小分類になければ、シラバス上で別の小分類に置かれていないかを名前だけで探す
                best = (None, [], None)
                for other, it in all_items:
                    cand, h = match_item(name, name, [it])
                    if cand and len(h) > len(best[1]):
                        best = (cand, h, other)
                item, hits, where = best
            note_rows.append({"code": code, "note": name, "item": item["name"] if item else None,
                              "hits": hits, "where": where})
            if item:
                covered.add((where, item["name"]))
    note_covered = len(covered)
    covered |= set(direct or {})
    uncovered = [(code, it["name"], len(item_terms(it))) for code, it in all_items if (code, it["name"]) not in covered]
    return {"notes": note_rows, "uncovered": uncovered, "total_items": len(all_items),
            "covered_items": len(all_items) - len(uncovered), "note_covered": note_covered,
            "direct_count": len(direct or {})}


def build_check_report(result: dict, syllabus: dict) -> str:
    smalls = small_categories(syllabus)
    notes = result["notes"]
    same = [n for n in notes if n["item"] and n["where"] == n["code"]]
    moved = [n for n in notes if n["item"] and n["where"] != n["code"]]
    outside = [n for n in notes if not n["item"]]
    pct = lambda a, b: f"{a / b:.1%}"
    lines = ["# シラバス照合レポート（AP 科目A）", "",
             "`python scripts/syllabus.py check --out docs/syllabus_check.md` で生成。",
             "照合元：data/syllabus_A.json（ユーザー提示。シラバス Ver.7.2 から抽出）。",
             "照合方法：学習項目の名前・要点と、シラバス項目の名前・用語例の一致語を数える機械照合。"
             "同じ小分類で見つからなければ、全小分類から名前で探す。用語例は「例」なので、載っていない語が出題範囲外とは限らない。", "",
             "## 1. 集計（実測）", "",
             "| 区分 | 件数 | 割合 |", "| --- | ---: | ---: |",
             f"| 学習項目：同じ小分類のシラバス項目に対応 | {len(same)} | {pct(len(same), len(notes))} |",
             f"| 学習項目：シラバスでは別の小分類に置かれている | {len(moved)} | {pct(len(moved), len(notes))} |",
             f"| 学習項目：シラバスの用語例に見当たらない | {len(outside)} | {pct(len(outside), len(notes))} |",
             f"| シラバス項目：学習項目が触れている | {result['note_covered']} / {result['total_items']} | "
             f"{pct(result['note_covered'], result['total_items'])} |",
             f"| シラバス項目：syllabus_points.csv で直接補った | {result['direct_count']} / {result['total_items']} | "
             f"{pct(result['direct_count'], result['total_items'])} |",
             f"| シラバス項目：要点あり（合計） | {result['covered_items']} / {result['total_items']} | "
             f"{pct(result['covered_items'], result['total_items'])} |", "",
             "## 2. シラバスでは別の小分類に置かれている学習項目", "",
             "| 学習項目のコード | 学習項目 | シラバスのコード | シラバス項目 | 一致した語 |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {n['code']} | {n['note']} | {n['where']} | {n['item']} | {'、'.join(n['hits'][:4])} |" for n in moved]
    lines += ["", "## 3. シラバスの用語例に見当たらない学習項目（表現の確認候補）", "",
              "| コード | 学習項目 |", "| --- | --- |"]
    lines += [f"| {n['code']} | {n['note']} |" for n in outside]
    lines += ["", "## 4. 要点がまだないシラバス項目", "",
              "| コード | 小分類 | シラバス項目 | 用語例の数 |", "| --- | --- | --- | ---: |"]
    for code, item, n in result["uncovered"]:
        lines.append(f"| {code} | {smalls[code]['name'].split(' ', 1)[1]} | {item} | {n} |")
    lines += ["", "## 5. 対応表（学習項目 → シラバス項目：一致した語）", "",
              "| コード | 学習項目 | シラバス | 一致した語 |", "| --- | --- | --- | --- |"]
    lines += [f"| {n['code']} | {n['note']} | {(n['where'] + ' ' + n['item']) if n['item'] else '—'} | {'、'.join(n['hits'][:6])} |"
              for n in notes]
    return "\n".join(lines) + "\n"


def build_book(syllabus: dict, notes: dict[str, list[tuple[str, str]]], direct: dict) -> str:
    """シラバスの並び（中分類→小分類→項目）で、用語例と要点をまとめる。"""
    result = check(syllabus, notes, direct)
    by_item: dict[tuple[str, str], list[str]] = {}
    for n in result["notes"]:
        if n["item"]:
            point = dict(notes[n["code"]])[n["note"]]
            moved = f"（学習項目 {n['code']} から）" if n["where"] != n["code"] else ""
            by_item.setdefault((n["where"], n["item"]), []).append(f"**{n['note']}**{moved}：{point}")
    lines = ["# AP 科目A 学習ノート（シラバス Ver.7.2 の並び）", "",
             "`python scripts/syllabus.py book --out docs/ap_syllabus_book.md` で生成。",
             "構成と用語例：data/syllabus_A.json（ユーザー提示、シラバス Ver.7.2 から抽出）。"
             "要点：Claude 作成（推定。数値例はコードで検算済み）。用語例は長いものを省略して表示する。", ""]
    for field in syllabus["children"]:
        for major in field["children"]:
            for mid in major["children"]:
                lines += [f"## {mid['name']}（{field['name']}・{major['name']}）", ""]
                for small in mid["children"]:
                    lines += [f"### {small['name']}", ""]
                    for item in small["items"]:
                        key = (small["code"], item["name"])
                        terms = item_terms(item)
                        lines.append(f"#### {item['name']}")
                        if terms:
                            shown = "、".join(terms[:20]) + (f" ほか{len(terms) - 20}語" if len(terms) > 20 else "")
                            lines.append(f"用語例：{shown}")
                        lines.append("")
                        points = by_item.get(key, []) + ([direct[key]] if key in direct else [])
                        lines += [f"- {p}" for p in points] or ["- （要点なし）"]
                        lines.append("")
    return "\n".join(lines)


def build_tree(syllabus: dict, with_terms: bool = False) -> str:
    lines = [f"{syllabus['title']}（出典：{syllabus['source']}）"]

    def walk(nodes, prefix):
        for i, node in enumerate(nodes):
            last = i == len(nodes) - 1
            head, cont = prefix + ("└─ " if last else "├─ "), prefix + ("   " if last else "│  ")
            if "items" in node:  # 小分類：項目を1行に並べる
                names = []
                for it in node["items"]:
                    names.append(it["name"] + (f"（{'、'.join(item_terms(it))}）" if with_terms and item_terms(it) else ""))
                lines.append(f"{head}{node['name']}：{' ／ '.join(names)}")
            else:
                lines.append(f"{head}{node['name']}")
                walk(node.get("children", []), cont)

    walk(syllabus["children"], "")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("command", choices=("tree", "check", "book"))
    p.add_argument("--terms", action="store_true", help="tree で用語例も表示する")
    p.add_argument("--out", type=Path)
    args = p.parse_args(argv)
    syllabus = load_syllabus()
    if args.command == "tree":
        text = build_tree(syllabus, args.terms)
    elif args.command == "check":
        text = build_check_report(check(syllabus, load_notes(), load_syllabus_points()), syllabus)
    else:
        text = build_book(syllabus, load_notes(), load_syllabus_points())
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"出力しました: {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
