"""AP 科目Aの演習エンジン。問題バンクから出題し、結果を data/log_A.csv に記録する。

流れ（通常モード）:
  本問を解く → 誤答または確信度C（不明）なら、正解・解説を見て解析を記録
  → 関連問題を最大3問（同じ中分類、同じ小分類を優先）。2問続けて正解したら2問で打ち切り
  → 次の本問へ。関連問題で間違えても、そこからさらに関連問題は出さない（無限に続かないように）。
問題数の上限（--count）は本問と関連の合計で数える（1日の所要時間を計画内に収めるため）。

通し演習（--exam）: 本番と同じく途中では正誤を見せない。解き終えてから誤答の解説と解析を行う。
関連問題は出さず、翌日の最初の30分に --weak 3（誤答上位3中分類）で解く。

使い方:
  python scripts/quiz.py --mid 09            # 中分類09から出題（P1 分野別演習）
  python scripts/quiz.py --source 令和6年度秋期 --exam   # 年度別の通し（P2）
  python scripts/quiz.py --weak 3            # 誤答数上位3中分類（翌朝30分・P3）
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import analyze_A
import aplib
import qbank
from add_log import Aborted, ask, parse_cause, parse_confidence

ANSWER_ALIASES = {
    "ア": "ア", "イ": "イ", "ウ": "ウ", "エ": "エ",
    "a": "ア", "i": "イ", "u": "ウ", "e": "エ",
    "1": "ア", "2": "イ", "3": "ウ", "4": "エ",
}
MAX_RELATED = 3
STOP_AFTER_CORRECT = 2


def parse_answer(raw: str) -> str:
    v = ANSWER_ALIASES.get(raw.lower())
    if v is None:
        raise ValueError("ア/イ/ウ/エ（a/i/u/e、1〜4 でも可）で入力してください")
    return v


def parse_note(raw: str) -> str:
    if raw == ".":
        return "DB解説参照"
    if not raw:
        raise ValueError("1行で書いてください（DBの解説どおりなら . ）")
    return raw


class Session:
    def __init__(self, pool, log_rows, log_path: Path, *, input_fn=input, output_fn=print,
                 clock=time.monotonic, today: date | None = None, exam=False, quota=40):
        self.pool = pool
        self.log_path = log_path
        self.input, self.out, self.clock = input_fn, output_fn, clock
        self.today = (today or date.today()).isoformat()
        self.exam, self.quota = exam, quota
        self.seen_count = Counter(r["問題ID"] for r in log_rows if r["問題ID"])
        self.used: set[str] = set()
        self.asked = 0
        self.results: list[dict] = []

    # --- 入出力 ---
    def q(self, prompt, parse):
        return ask(prompt, parse, self.input, self.out)

    def show(self, question, label):
        self.out("")
        self.out(f"【{label}】{question['id']}  {question['code']} {question['mid']} / {question['small']}  出典: {question['source']}")
        if question["has_figure"]:
            self.out("  ※ 図表あり。原本の図を確認してください")
        if question.get("note"):
            self.out(f"  ※ {question['note']}")
        self.out(question["stem"])
        for k, v in question["choices"].items():
            self.out(f"  {k} {v}")

    def explain(self, question):
        self.out(f"  正解は {question['answer']}：{question['choices'][question['answer']]}")
        if question["explanation"]:
            self.out(f"  解説（{question['explanation_author'] or '作成者未記入'}）：{question['explanation']}")
        else:
            self.out("  解説：未登録です（下のリンク先で確認してください）")
        for link in question["links"]:
            self.out(f"  参考：{link['site']} {link['url']}")

    # --- 1問 ---
    def solve(self, question, kind, label) -> dict:
        self.used.add(question["id"])
        self.asked += 1
        self.show(question, label)
        t0 = self.clock()
        answer = self.q("解答: ", parse_answer)
        conf = self.q("確信度 A=確信 / B=半々 / C=勘（不明）: ", parse_confidence)
        row = {
            "日付": self.today, "出典": question["source"], "問番号": question["id"], "コード": question["code"],
            "確信度": conf, "正誤": "正" if answer == question["answer"] else "誤", "原因": "",
            "正解の根拠": "", "誤選択肢が違う理由": "", "解答秒": str(round(self.clock() - t0)), "分析秒": "0",
            "問題ID": question["id"], "種別": kind,
        }
        result = {"question": question, "row": row, "answer": answer}
        if not self.exam:
            self.review(result)
        return result

    def review(self, result):
        """正誤を伝え、誤答・実質誤答なら解説と解析を記録してログに書く。"""
        question, row = result["question"], result["row"]
        t1 = self.clock()
        wrong = aplib.is_effective_wrong(row)
        if row["正誤"] == "正":
            self.out("  ○ 正解" + ("（ただし確信度Cなので実質誤答として扱います）" if wrong else ""))
        else:
            self.out(f"  × 不正解（あなたの解答：{result['answer']}）")
        if wrong:
            self.explain(question)
            menu = " / ".join(f"{i}={c}" for i, c in enumerate(aplib.CAUSES, start=1))
            row["原因"] = self.q(f"原因 {menu}: ", parse_cause)
            row["正解の根拠"] = self.q("正解の根拠（自分の言葉で1行、. でDB解説どおり）: ", parse_note)
            row["誤選択肢が違う理由"] = self.q("誤選択肢が違う理由（. でDB解説どおり）: ", parse_note)
        elif self.input("  Enter=次へ / e=解説を見る: ").strip().lower() == "e":
            self.explain(question)
            self.input("  Enter=次へ: ")
        row["分析秒"] = str(round(self.clock() - t1))
        aplib.append_row(self.log_path, aplib.LOG_A_COLUMNS, row)
        self.results.append(result)

    def related_chain(self, question):
        """関連問題を最大3問。2問続けて正解したら打ち切る。関連問題からはさらに派生させない。"""
        streak = 0
        for i in range(1, MAX_RELATED + 1):
            if self.asked >= self.quota:
                self.out("  （今日の問題数の上限に達したため、関連問題を打ち切ります）")
                return
            cands = qbank.rank_related(question, self.pool, self.used, self.seen_count)
            if not cands:
                if i == 1:
                    self.out(f"  関連問題がバンクにありません（中分類 {question['mid_no']}）。追加候補として控えてください")
                return
            res = self.solve(cands[0], "関連", f"関連 {i}/{MAX_RELATED}  元: {question['id']}")
            streak = 0 if aplib.is_effective_wrong(res["row"]) else streak + 1
            if streak >= STOP_AFTER_CORRECT:
                self.out("  関連問題を2問続けて正解したので、次の本問へ進みます")
                return

    # --- 全体 ---
    def run(self, mains) -> list[dict]:
        pending = []
        try:
            for n, question in enumerate(mains, start=1):
                if self.asked >= self.quota:
                    break
                res = self.solve(question, "本問", f"本問 {n}/{min(len(mains), self.quota)}")
                if self.exam:
                    pending.append(res)
                elif aplib.is_effective_wrong(res["row"]):
                    self.related_chain(question)
        except (Aborted, EOFError, KeyboardInterrupt):
            self.out("\n中断しました（解き終えた問題は記録済みです）")
        if self.exam and pending:
            self.out(f"\n=== 通し終了：{len(pending)}問。ここから答え合わせと解析 ===")
            try:
                for res in pending:
                    self.out(f"\n{res['question']['id']}（{res['question']['code']}）")
                    self.review(res)
            except (Aborted, EOFError, KeyboardInterrupt):
                self.out("\n答え合わせを中断しました（ここまでの分は記録済み。残りは記録されていません）")
        self.summary()
        return self.results

    def summary(self):
        mains = [r["row"] for r in self.results if r["row"]["種別"] == "本問"]
        rel = [r["row"] for r in self.results if r["row"]["種別"] == "関連"]
        wrong = sum(aplib.is_effective_wrong(r) for r in mains)
        secs = sum(int(r["解答秒"]) + int(r["分析秒"]) for r in mains + rel)
        self.out("")
        self.out(f"本日の記録：本問 {len(mains)}問（実質誤答 {wrong}）＋ 関連 {len(rel)}問、所要 {secs / 60:.1f}分")
        if self.exam:
            self.out("関連問題は翌日の最初の30分に `python scripts/quiz.py --weak 3` で解いてください")


def select_mains(pool, log_rows, taxonomy, *, mids=None, source=None, weak=0, include_seen=False):
    """本問の候補。既定では、一度でも解いた問題（本問・関連とも）は除く。"""
    seen = {r["問題ID"] for r in log_rows if r["問題ID"]}
    if weak:
        stats = analyze_A.middle_stats([r for r in log_rows if r["種別"] == "本問"], taxonomy)
        mids = [s.mid for s in analyze_A.top_wrong(stats, weak)]
        if not mids:
            return []
    qs = [q for q in pool
          if (not mids or q["mid_no"] in mids)
          and (not source or source in q["source"])
          and (include_seen or q["id"] not in seen)]
    return sorted(qs, key=lambda q: (q["mid_no"], q["id"])) if not source else qs


RESERVED_PATH = aplib.DATA_DIR / "reserved_exams.txt"


def load_reserved(path: Path = RESERVED_PATH) -> list[str]:
    """通し演習のために取っておく回（出典に含まれる文字列）の一覧。"""
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]


def drill_pool(pool, reserved: list[str]):
    """分野別・弱点演習で使う問題（取っておく回を除く）。初見の通しを関連問題で崩さないため。"""
    return [q for q in pool if not any(r in q["source"] for r in reserved)]


def default_quota(plan: dict[str, int], today: str) -> int:
    return plan.get(today, 40)


def main(argv=None, input_fn=input, output_fn=print, clock=time.monotonic, today: date | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--mid", help="中分類番号（カンマ区切り、例 09,10）")
    p.add_argument("--source", help="出典に含まれる文字列（例 令和6年度秋期）")
    p.add_argument("--weak", type=int, default=0, help="誤答数上位N中分類から出題")
    p.add_argument("--exam", action="store_true", help="通し演習：途中で正誤を見せない")
    p.add_argument("--count", type=int, help="問題数の上限（本問＋関連）。既定は plan_A.csv の当日計画、なければ40")
    p.add_argument("--include-seen", action="store_true", help="解いたことのある問題も本問に含める")
    p.add_argument("--use-reserved", action="store_true", help="通し用に取っておく回（data/reserved_exams.txt）も分野別で使う")
    p.add_argument("--log", type=Path, default=aplib.LOG_A_PATH)
    p.add_argument("--db", type=Path, default=qbank.DB_PATH)
    p.add_argument("--dir", type=Path, default=qbank.QUESTIONS_DIR)
    args = p.parse_args(argv)

    taxonomy = aplib.load_taxonomy()
    pool = qbank.fetch_questions(qbank.ensure_db(args.db, args.dir, taxonomy))
    log_rows, warnings = aplib.read_log_a(args.log, taxonomy)
    for w in warnings:
        output_fn(f"警告: {w}")
    day = today or date.today()
    mids = [f"{int(m):02d}" for m in args.mid.split(",")] if args.mid else None
    if not args.source and not args.use_reserved:
        reserved = load_reserved()
        pool = drill_pool(pool, reserved)
        if reserved:
            output_fn(f"通し用に取っておく回（{len(reserved)}回）は使いません：{'、'.join(reserved)}")
    mains = select_mains(pool, log_rows, taxonomy, mids=mids, source=args.source,
                         weak=args.weak, include_seen=args.include_seen)
    if not mains:
        output_fn("条件に合う未出題の問題がありません（--include-seen で既出も対象にできます）")
        return 1
    quota = args.count or (len(mains) if args.exam else default_quota(analyze_A.load_plan(aplib.PLAN_A_PATH), day.isoformat()))
    output_fn(f"AP 科目A 演習：候補 {len(mains)}問、上限 {quota}問（本問＋関連）。q で中断")
    Session(pool, log_rows, args.log, input_fn=input_fn, output_fn=output_fn, clock=clock,
            today=day, exam=args.exam, quota=quota).run(mains)
    return 0


if __name__ == "__main__":
    sys.exit(main())
