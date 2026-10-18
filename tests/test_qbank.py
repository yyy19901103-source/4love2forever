import json
import sqlite3

import aplib
import qbank

TAX = aplib.load_taxonomy()


def make_q(id, code="09-3", stem="SQLの集約", answer="イ", **kw):
    q = {"id": id, "origin": "自作", "source": "テスト", "code": code, "stem": stem,
         "choices": {"ア": "a", "イ": "b", "ウ": "c", "エ": "d"}, "answer": answer,
         "explanation": "", "keywords": [], "links": []}
    q.update(kw)
    return q


def write_jsonl(path, qs):
    path.write_text("\n".join(json.dumps(q, ensure_ascii=False) for q in qs) + "\n", encoding="utf-8")
    return path


def test_seed_bank_is_valid():
    qs, errors = qbank.load_questions(qbank.question_files(), TAX)
    assert errors == []
    assert len(qs) >= 15 and all(q["origin"] == "自作" for q in qs)


def test_validation_errors(tmp_path):
    bad = [
        make_q("A1", code="99-1"),
        make_q("A2", answer="オ"),
        make_q("A3", choices={"ア": "a", "イ": "b", "ウ": "c"}),
        make_q("A4", origin="IPA過去問"),                         # 出典URLなし
        make_q("A5", links=[{"site": "x", "url": "http://x"}]),   # https でない
        make_q("A6"), make_q("A6"),                               # id 重複
        make_q("A 7"),
    ]
    p = write_jsonl(tmp_path / "bad.jsonl", bad)
    p.write_text(p.read_text(encoding="utf-8") + "{壊れたJSON\n", encoding="utf-8")
    qs, errors = qbank.load_questions([p], TAX)
    assert [q["id"] for q in qs] == ["A6"]
    text = "\n".join(errors)
    for msg in ("taxonomy", "answer", "choices", "出典URL", "https://", "重複", "英数字", "JSON"):
        assert msg in text


def test_build_and_fetch_roundtrip(tmp_path):
    src = write_jsonl(tmp_path / "q.jsonl", [
        make_q("Q1", keywords=["HAVING"], links=[{"site": "IPA", "url": "https://example.jp/q1"}], has_figure=True)])
    db = tmp_path / "bank.sqlite"
    n, errors = qbank.build(db, [src], TAX)
    assert (n, errors) == (1, [])
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM taxonomy").fetchone()[0] == 96
    con.row_factory = sqlite3.Row
    q = qbank.fetch_questions(con)[0]
    assert q["choices"] == {"ア": "a", "イ": "b", "ウ": "c", "エ": "d"}
    assert (q["mid_no"], q["small"], q["has_figure"], q["keywords"]) == ("09", "データ操作", 1, "HAVING")
    assert q["links"] == [{"site": "IPA", "url": "https://example.jp/q1"}]


def test_build_refuses_on_error_and_keeps_old_db(tmp_path):
    db = tmp_path / "bank.sqlite"
    qbank.build(db, [write_jsonl(tmp_path / "ok.jsonl", [make_q("Q1")])], TAX)
    n, errors = qbank.build(db, [write_jsonl(tmp_path / "ng.jsonl", [make_q("Q2", code="00-0")])], TAX)
    assert n == 0 and errors
    assert sqlite3.connect(db).execute("SELECT id FROM questions").fetchall() == [("Q1",)]


def test_ensure_db_rebuilds_when_jsonl_is_newer(tmp_path):
    d = tmp_path / "questions"
    d.mkdir()
    write_jsonl(d / "a.jsonl", [make_q("Q1")])
    db = tmp_path / "bank.sqlite"
    assert len(qbank.fetch_questions(qbank.ensure_db(db, d, TAX))) == 1
    import os, time
    write_jsonl(d / "b.jsonl", [make_q("Q2")])
    future = time.time() + 10
    os.utime(d / "b.jsonl", (future, future))
    assert len(qbank.fetch_questions(qbank.ensure_db(db, d, TAX))) == 2


def pool_item(id, code, stem="", keywords=""):
    return {"id": id, "code": code, "mid_no": code[:2], "stem": stem, "keywords": keywords}


def test_rank_related_order():
    target = pool_item("T", "09-3", "GROUP BY と HAVING で集約後に絞り込む")
    pool = [target,
            pool_item("S1", "09-3", "表の直積の行数"),
            pool_item("S2", "09-3", "GROUP BY で集約後に HAVING で絞り込む条件"),
            pool_item("M1", "09-4", "GROUP BY と HAVING で集約後に絞り込む"),  # 文面は同じだが小分類が違う
            pool_item("X1", "11-1", "GROUP BY と HAVING")]                      # 中分類が違うので対象外
    assert [q["id"] for q in qbank.rank_related(target, pool, set(), {})] == ["S2", "S1", "M1"]
    # 解いた回数が少ない問題を優先し、使用済みは除く
    assert [q["id"] for q in qbank.rank_related(target, pool, {"S1"}, {"S2": 2})] == ["S2", "M1"]
    assert [q["id"] for q in qbank.rank_related(target, pool[:3] + pool[3:], set(), {"S2": 1})][:2] == ["S1", "S2"]


def test_similarity_bounds():
    a = pool_item("a", "09-3", "HAVING句")
    assert qbank.similarity(a, a) == 1.0
    assert qbank.similarity(a, pool_item("b", "09-3", "公開鍵暗号")) == 0.0


def test_seed_bank_covers_every_middle_category_and_answers_are_balanced():
    from collections import Counter
    qs, errors = qbank.load_questions(qbank.question_files(), TAX)
    assert errors == []
    per_mid = Counter(TAX[q["code"]]["中分類番号"] for q in qs)
    assert set(per_mid) == set(aplib.middle_categories(TAX))
    assert min(per_mid.values()) >= 3  # 関連問題を出せるよう、各中分類に3問以上
    answers = Counter(q["answer"] for q in qs)
    assert max(answers.values()) / len(qs) <= 0.35  # 1つの記号に偏ると当て推量で正解できてしまう
