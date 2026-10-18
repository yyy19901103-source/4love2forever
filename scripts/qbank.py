"""AP 科目Aの問題バンク（SQLite）。

正本は data/questions/*.jsonl（1行1問、git で差分を追える形式）。SQLite はそこから作る派生物で、
JSONL が新しければ自動で作り直す。

使い方:
  python scripts/qbank.py build            # JSONL → data/ap_bank.sqlite
  python scripts/qbank.py check FILE.jsonl # 取り込み前の検証だけ行う
  python scripts/qbank.py stats            # 中分類ごとの収録数（関連問題が出せるかの目安）

1問の形式（JSONL の1行）:
  {"id": "AP-R06A-01", "origin": "IPA過去問", "source": "令和6年度秋期 AP 午前 問1",
   "code": "01-1", "stem": "問題文", "choices": {"ア": "...", "イ": "...", "ウ": "...", "エ": "..."},
   "answer": "ウ", "explanation": "自作の解説", "explanation_author": "Claude",
   "keywords": ["..."], "links": [{"site": "IPA", "url": "https://..."}], "has_figure": false}
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

import aplib

QUESTIONS_DIR = aplib.DATA_DIR / "questions"
DB_PATH = aplib.DATA_DIR / "ap_bank.sqlite"
CHOICE_LABELS = ("ア", "イ", "ウ", "エ")
ORIGINS = ("IPA過去問", "自作")
REQUIRED = ("id", "origin", "source", "code", "stem", "choices", "answer")

SCHEMA = """
CREATE TABLE taxonomy (
  code TEXT PRIMARY KEY, field TEXT, major TEXT, mid_no TEXT, mid TEXT, small_no TEXT, small TEXT
);
CREATE TABLE questions (
  id TEXT PRIMARY KEY,
  origin TEXT NOT NULL CHECK (origin IN ('IPA過去問', '自作')),
  source TEXT NOT NULL,
  code TEXT NOT NULL REFERENCES taxonomy(code),
  stem TEXT NOT NULL,
  choice_a TEXT NOT NULL, choice_i TEXT NOT NULL, choice_u TEXT NOT NULL, choice_e TEXT NOT NULL,
  answer TEXT NOT NULL CHECK (answer IN ('ア', 'イ', 'ウ', 'エ')),
  explanation TEXT NOT NULL DEFAULT '',
  explanation_author TEXT NOT NULL DEFAULT '',
  keywords TEXT NOT NULL DEFAULT '',
  has_figure INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE links (
  question_id TEXT NOT NULL REFERENCES questions(id), site TEXT NOT NULL, url TEXT NOT NULL
);
CREATE INDEX idx_questions_code ON questions(code);
"""


def validate_question(q: dict, taxonomy) -> list[str]:
    errors = [f"{k} がありません" for k in REQUIRED if k not in q]
    if errors:
        return errors
    if not re.fullmatch(r"[A-Za-z0-9-]+", str(q["id"])):
        errors.append(f"id は英数字とハイフンだけです: {q['id']!r}")
    if q["origin"] not in ORIGINS:
        errors.append(f"origin は {'/'.join(ORIGINS)} のいずれかです: {q['origin']!r}")
    if q["code"] not in taxonomy:
        errors.append(f"code {q['code']!r} は taxonomy.csv にありません")
    if not str(q["stem"]).strip():
        errors.append("stem が空です")
    choices = q["choices"]
    if not isinstance(choices, dict) or sorted(choices) != sorted(CHOICE_LABELS):
        errors.append("choices は ア/イ/ウ/エ の4つちょうどです")
    elif not all(str(v).strip() for v in choices.values()):
        errors.append("空の選択肢があります")
    if q["answer"] not in CHOICE_LABELS:
        errors.append(f"answer は ア/イ/ウ/エ のいずれかです: {q['answer']!r}")
    if q["origin"] == "IPA過去問" and not q.get("links"):
        errors.append("IPA過去問には出典URL（links）を1つ以上付けてください")
    for link in q.get("links", []):
        if not str(link.get("url", "")).startswith("https://"):
            errors.append(f"links の url は https:// で始めてください: {link!r}")
    return errors


def load_questions(paths, taxonomy) -> tuple[list[dict], list[str]]:
    """JSONL を読み、(正常な問題, エラー) を返す。id の重複もエラーにする。"""
    questions, errors, seen = [], [], set()
    for path in paths:
        for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            where = f"{Path(path).name}:{lineno}"
            try:
                q = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"{where} JSONとして読めません: {e}")
                continue
            errs = validate_question(q, taxonomy)
            if q.get("id") in seen:
                errs.append(f"id {q['id']!r} が重複しています")
            if errs:
                errors.extend(f"{where} {e}" for e in errs)
                continue
            seen.add(q["id"])
            questions.append(q)
    return questions, errors


def question_files(directory: Path = QUESTIONS_DIR) -> list[Path]:
    return sorted(directory.glob("*.jsonl"))


def build(db_path: Path, paths, taxonomy) -> tuple[int, list[str]]:
    """JSONL から SQLite を作り直す。エラーが1つでもあれば作らない。"""
    questions, errors = load_questions(paths, taxonomy)
    if errors:
        return 0, errors
    tmp = db_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    with con:
        con.executescript(SCHEMA)
        con.executemany("INSERT INTO taxonomy VALUES (?,?,?,?,?,?,?)", [
            (r["コード"], r["分野"], r["大分類"], r["中分類番号"], r["中分類"], r["小分類番号"], r["小分類"])
            for r in taxonomy.values()])
        for q in questions:
            c = q["choices"]
            con.execute("INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                q["id"], q["origin"], q["source"], q["code"], q["stem"],
                c["ア"], c["イ"], c["ウ"], c["エ"], q["answer"],
                q.get("explanation", ""), q.get("explanation_author", ""),
                " ".join(q.get("keywords", [])), int(bool(q.get("has_figure")))))
            con.executemany("INSERT INTO links VALUES (?,?,?)",
                            [(q["id"], l["site"], l["url"]) for l in q.get("links", [])])
    con.close()
    tmp.replace(db_path)
    return len(questions), []


def ensure_db(db_path: Path = DB_PATH, directory: Path = QUESTIONS_DIR, taxonomy=None) -> sqlite3.Connection:
    """JSONL より古ければ作り直してから接続を返す。"""
    taxonomy = taxonomy or aplib.load_taxonomy()
    paths = question_files(directory)
    newest = max((p.stat().st_mtime for p in paths), default=0)
    if not db_path.exists() or db_path.stat().st_mtime < newest:
        _, errors = build(db_path, paths, taxonomy)
        if errors:
            raise ValueError("問題バンクを作れません:\n" + "\n".join(errors))
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def fetch_questions(con: sqlite3.Connection) -> list[dict]:
    rows = [dict(r) for r in con.execute(
        "SELECT q.*, t.mid_no, t.mid, t.small FROM questions q JOIN taxonomy t USING (code) ORDER BY q.id")]
    links: dict[str, list] = {}
    for r in con.execute("SELECT * FROM links"):
        links.setdefault(r["question_id"], []).append({"site": r["site"], "url": r["url"]})
    for r in rows:
        r["choices"] = dict(zip(CHOICE_LABELS, (r.pop("choice_a"), r.pop("choice_i"), r.pop("choice_u"), r.pop("choice_e"))))
        r["links"] = links.get(r["id"], [])
    return rows


def bigrams(text: str) -> set[str]:
    t = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))
    return {t[i:i + 2] for i in range(len(t) - 1)}


def similarity(a: dict, b: dict) -> float:
    """問題文＋キーワードの文字2-gram の Jaccard 係数（0〜1）。日本語でも形態素解析なしで使える。"""
    x, y = bigrams(a["stem"] + a["keywords"]), bigrams(b["stem"] + b["keywords"])
    return len(x & y) / len(x | y) if x | y else 0.0


def rank_related(target: dict, pool: list[dict], exclude: set[str], seen_count: dict[str, int]) -> list[dict]:
    """関連問題の候補を近い順に返す。

    同じ中分類の問題だけを候補にし、(1) 同じ小分類 → (2) 解いた回数が少ない → (3) 問題文が似ている → (4) id 順。
    """
    cand = [q for q in pool if q["id"] != target["id"] and q["id"] not in exclude and q["mid_no"] == target["mid_no"]]
    return sorted(cand, key=lambda q: (q["code"] != target["code"], seen_count.get(q["id"], 0),
                                       -similarity(target, q), q["id"]))


def coverage(questions: list[dict], taxonomy) -> list[tuple[str, str, int, int]]:
    """中分類ごとの (番号, 名称, 収録数, 収録のある小分類数)。"""
    out = []
    for mid, name in aplib.middle_categories(taxonomy).items():
        qs = [q for q in questions if q["mid_no"] == mid]
        out.append((mid, name, len(qs), len({q["code"] for q in qs})))
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("command", choices=("build", "check", "stats"))
    p.add_argument("files", nargs="*", type=Path, help="check の対象（省略時は data/questions/*.jsonl）")
    p.add_argument("--db", type=Path, default=DB_PATH)
    p.add_argument("--dir", type=Path, default=QUESTIONS_DIR)
    args = p.parse_args(argv)
    taxonomy = aplib.load_taxonomy()

    if args.command == "check":
        qs, errors = load_questions(args.files or question_files(args.dir), taxonomy)
        for e in errors:
            print(f"! {e}")
        print(f"正常 {len(qs)}問、エラー {len(errors)}件")
        return 1 if errors else 0
    if args.command == "build":
        n, errors = build(args.db, question_files(args.dir), taxonomy)
        for e in errors:
            print(f"! {e}")
        print(f"作成しました: {args.db}（{n}問）" if not errors else "エラーがあるため作成しませんでした")
        return 1 if errors else 0
    con = ensure_db(args.db, args.dir, taxonomy)
    qs = fetch_questions(con)
    print(f"収録 {len(qs)}問（IPA過去問 {sum(q['origin'] == 'IPA過去問' for q in qs)}、自作 {sum(q['origin'] == '自作' for q in qs)}）")
    print("| 中分類 | 名称 | 収録数 | 収録のある小分類数 |")
    print("| --- | --- | ---: | ---: |")
    for mid, name, n, smalls in coverage(qs, taxonomy):
        print(f"| {mid} | {name} | {n} | {smalls} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
