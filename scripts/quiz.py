"""AP 科目Aの演習エンジン。問題バンクから出題し、結果を data/log_A.csv に記録する。

流れ（通常モード）:
  本問を解く → 誤答または確信度C（不明）なら、正解・解説を見て解析を記録
  → 関連問題を最大3問（同じ中分類、同じ小分類を優先）。2問続けて正解したら2問で打ち切り
  → 次の本問へ。関連問題で間違えても、そこからさらに関連問題は出さない（無限に続かないように）。
問題数の上限（--count）は本問と関連の合計で数える（1日の所要時間を計画内に収めるため）。

通し演習（--exam）: 本番と同じく途中では正誤を見せない。解き終えてから誤答の解説と解析を行う。関連問題は出さない。
  --sheet（解答用紙モード）: 問題文を表示せず、原本 PDF（または紙）で解いた解答と確信度だけを「イA」のように入力する。
    図のある問題は OCR の本文が崩れるので、通しはこのモードを勧める。1問解くごとに入力すると解答秒が1問ずつ測れる。
  答え合わせの途中で中断しても、残りの解答はログと同じ場所の *.pending.json に保存される。--resume で続きから答え合わせする。
解き直し（--review）: review_queue.py の一覧（前日・3日前の誤答と確信度C）を出題する。関連問題は出さない。

ログには 日目・種別・初見 を付けて記録する。種別は --exam＝通し、--weak＝弱点、--review＝復習、それ以外＝分野別。
初見は、同じ問題（出典・問番号）がログにあれば N、なければ Y（復習は常に N）。
関連問題も同じ種別で記録する（解説を読んだ直後の類題なので、初見でも正答率がやや高めに出る点に注意）。

使い方:
  python scripts/quiz.py --day 1 --source 令和7年度秋期 --exam --sheet    # 1日目：基準通し（原本 PDF で解き、解答だけ入力）
  python scripts/quiz.py --day 1 --resume                                # 中断した答え合わせの続き
  python scripts/quiz.py --day 2 --mid 11 --count 40                     # 分野別
  python scripts/quiz.py --day 7 --weak 3                                # 誤答数上位3中分類
  python scripts/quiz.py --day 8 --review                                # 最初の15分の解き直し
  python scripts/quiz.py --day 16 --review --all                         # これまでの誤答と確信度Cをすべて解き直す
  python scripts/quiz.py --day 13 --source 令和4年度秋期 --exam --count 40 # 通しの前半40問（後半は翌日に同じ指定）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import analyze_A
import aplib
import qbank
import review_queue
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


def parse_sheet(raw: str) -> tuple[str, str]:
    """解答用紙モードの入力「イA」「2b」「i c」→ ("イ", "A") など。"""
    v = raw.replace(" ", "").replace("　", "")
    if len(v) < 2 or v[-1].upper() not in aplib.CONFIDENCE:
        raise ValueError("解答と確信度を続けて入力してください（例 イA、2b、uC）")
    return parse_answer(v[:-1]), v[-1].upper()


def parse_note(raw: str) -> str:
    if raw == ".":
        return "DB解説参照"
    if not raw:
        raise ValueError("1行で書いてください（DBの解説どおりなら . ）")
    return raw


class Session:
    def __init__(self, pool, log_rows, log_path: Path, *, input_fn=input, output_fn=print,
                 clock=time.monotonic, day: int = 1, kind: str = "分野別", quota=40, related=True, sheet=False):
        self.pool = pool
        self.log_path = log_path
        self.input, self.out, self.clock = input_fn, output_fn, clock
        self.day, self.kind, self.quota = day, kind, quota
        self.exam = kind == "通し"
        self.sheet = sheet and self.exam
        self.pending_path = pending_path(log_path)
        self.related = related and kind in ("分野別", "弱点")
        self.seen_keys = {aplib.question_key(r) for r in log_rows}
        self.seen_count = Counter(r["問番号"] for r in log_rows)
        self.used: set[str] = set()
        self.asked = 0
        self.results: list[dict] = []
        self.last_entry = None

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
    def solve(self, question, label, related=False) -> dict:
        self.used.add(question["id"])
        self.asked += 1
        if self.sheet:
            t0 = self.last_entry if self.last_entry is not None else self.clock()
            answer, conf = self.q(f"{label}  {question['source']}  解答＋確信度（例 イA）: ", parse_sheet)
            self.last_entry = self.clock()
        else:
            self.show(question, label)
            t0 = self.clock()
            answer = self.q("解答: ", parse_answer)
            conf = self.q("確信度 A=確信 / B=半々 / C=勘（不明）: ", parse_confidence)
        key = (question["source"], question["id"])
        row = {
            "日目": str(self.day), "種別": self.kind,
            "初見": "N" if self.kind == "復習" or key in self.seen_keys else "Y",
            "出典": question["source"], "問番号": question["id"], "コード": question["code"],
            "確信度": conf, "正誤": "正" if answer == question["answer"] else "誤", "原因": "",
            "正解の根拠": "", "誤選択肢が違う理由": "", "解答秒": str(round(self.clock() - t0)), "分析秒": "0",
        }
        self.seen_keys.add(key)
        result = {"question": question, "row": row, "answer": answer, "related": related}
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
            menu = " / ".join(f"{i}={c}" for i, c in enumerate(aplib.CAUSES, start=1))
            self.explain(question)
            row["原因"] = self.q(f"原因 {menu}: ", parse_cause)
        if aplib.needs_analysis(row):  # 誤答と確信度B/Cだけ分析する（確信度Aの正解は省く）
            if not wrong:
                self.explain(question)
            row["正解の根拠"] = self.q("正解の根拠（自分の言葉で1行、. で解説どおり）: ", parse_note)
            row["誤選択肢が違う理由"] = self.q("誤選択肢が違う理由（. で解説どおり）: ", parse_note)
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
            res = self.solve(cands[0], f"関連 {i}/{MAX_RELATED}  元: {question['id']}", related=True)
            streak = 0 if aplib.is_effective_wrong(res["row"]) else streak + 1
            if streak >= STOP_AFTER_CORRECT:
                self.out("  関連問題を2問続けて正解したので、次の本問へ進みます")
                return

    # --- 全体 ---
    def run(self, mains) -> list[dict]:
        pending = []
        if self.sheet:
            self.out("原本の問題を順に解き、1問ごとに解答と確信度を入力してください（例 イA）。q で中断")
            self.input("Enter で計時を始めます: ")
            self.last_entry = self.clock()
        try:
            for n, question in enumerate(mains, start=1):
                if self.asked >= self.quota:
                    break
                res = self.solve(question, f"{self.kind} {n}/{min(len(mains), self.quota)}")
                if self.exam:
                    pending.append(res)
                elif self.related and aplib.is_effective_wrong(res["row"]):
                    self.related_chain(question)
        except (Aborted, EOFError, KeyboardInterrupt):
            self.out("\n中断しました（解き終えた問題は記録済みです）")
        if self.exam and pending:
            self.out(f"\n=== 通し終了：{len(pending)}問。ここから答え合わせと解析 ===")
            correct = sum(r["row"]["正誤"] == "正" for r in pending)
            self.out(f"正答数 {correct}/{len(pending)}（基準 48/80）")
            self.grade(pending)
        self.summary()
        return self.results

    def grade(self, pending):
        """通しの答え合わせ。中断したら、残りを pending ファイルに保存する（--resume で再開）。"""
        save_pending(self.pending_path, pending)
        try:
            for i, res in enumerate(pending):
                self.out(f"\n{res['question']['id']}（{res['question']['code']}）")
                self.review(res)
                save_pending(self.pending_path, pending[i + 1:])
        except (Aborted, EOFError, KeyboardInterrupt):
            self.out(f"\n答え合わせを中断しました。残りの解答は {self.pending_path.name} に保存しました。"
                     f"`--day {self.day} --resume` で続きから答え合わせできます")

    def summary(self):
        mains = [r["row"] for r in self.results if not r["related"]]
        rel = [r["row"] for r in self.results if r["related"]]
        wrong = sum(aplib.is_effective_wrong(r) for r in mains)
        correct = sum(r["正誤"] == "正" for r in mains)
        secs = sum(int(r["解答秒"]) + int(r["分析秒"]) for r in mains + rel)
        self.out("")
        self.out(f"{self.day}日目（{self.kind}）の記録：{len(mains)}問（正解 {correct}、実質誤答 {wrong}）"
                 + (f"＋ 関連 {len(rel)}問" if rel else "") + f"、所要 {secs / 60:.1f}分")
        if self.exam:
            self.out("合格確率は `python scripts/pass_prob.py`、明日の解き直しは `python scripts/review_queue.py` で確認できます")


def pending_path(log_path: Path) -> Path:
    return log_path.with_name(log_path.stem + ".pending.json")


def save_pending(path: Path, pending) -> None:
    if not pending:
        path.unlink(missing_ok=True)
        return
    data = [{"id": r["question"]["id"], "answer": r["answer"], "row": r["row"]} for r in pending]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def load_pending(path: Path, pool) -> list[dict]:
    by_id = {q["id"]: q for q in pool}
    data = json.loads(path.read_text(encoding="utf-8"))
    return [{"question": by_id[d["id"]], "row": d["row"], "answer": d["answer"], "related": False} for d in data]


def select_mains(pool, log_rows, taxonomy, *, mids=None, source=None, weak=0, include_seen=False):
    """本問の候補。既定では、一度でも解いた問題（本問・関連とも）は除く。"""
    seen = {r["問番号"] for r in log_rows}
    if weak:
        stats = analyze_A.middle_stats([r for r in log_rows if r["初見"] == "Y"], taxonomy)
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


def default_quota(plan: dict[int, dict], day: int) -> int:
    return plan.get(day, {}).get("問題数", 40)


def review_mains(pool, log_rows, day: int, all_days: bool = False):
    """review_queue の一覧を問題バンクの問題に対応付ける（問題バンクにない手入力の問題は一覧だけ表示する）。"""
    by_id = {q["id"]: q for q in pool}
    queue = review_queue.build_queue(log_rows, day, all_days)
    return [by_id[x["問番号"]] for x in queue if x["問番号"] in by_id], [x for x in queue if x["問番号"] not in by_id]


def main(argv=None, input_fn=input, output_fn=print, clock=time.monotonic) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--day", type=int, required=True, help=f"今日の日目（1〜{aplib.PLAN_DAYS}）")
    p.add_argument("--mid", help="中分類番号（カンマ区切り、例 09,10）")
    p.add_argument("--source", help="出典に含まれる文字列（例 令和6年度秋期）")
    p.add_argument("--weak", type=int, default=0, help="誤答数上位N中分類から出題（種別＝弱点）")
    p.add_argument("--exam", action="store_true", help="通し演習：途中で正誤を見せない（種別＝通し）")
    p.add_argument("--review", action="store_true", help="前日・3日前の誤答と確信度Cを解き直す（種別＝復習）")
    p.add_argument("--all", action="store_true", help="--review と併用：これまでの誤答と確信度Cをすべて解き直す（16日目）")
    p.add_argument("--sheet", action="store_true", help="--exam と併用：問題文を出さず、原本で解いた解答と確信度だけを入力する")
    p.add_argument("--resume", action="store_true", help="中断した通しの答え合わせを続ける")
    p.add_argument("--no-related", action="store_true", help="誤答のあとの関連問題を出さない")
    p.add_argument("--count", type=int, help="問題数の上限（本問＋関連）。既定は plan_A.csv のその日目の問題数")
    p.add_argument("--include-seen", action="store_true", help="解いたことのある問題も本問に含める")
    p.add_argument("--use-reserved", action="store_true", help="通し用に取っておく回（data/reserved_exams.txt）も分野別で使う")
    p.add_argument("--log", type=Path, default=aplib.LOG_A_PATH)
    p.add_argument("--db", type=Path, default=qbank.DB_PATH)
    p.add_argument("--dir", type=Path, default=qbank.QUESTIONS_DIR)
    args = p.parse_args(argv)
    if not 1 <= args.day <= aplib.PLAN_DAYS:
        p.error(f"--day は 1〜{aplib.PLAN_DAYS} です")

    taxonomy = aplib.load_taxonomy()
    pool = qbank.fetch_questions(qbank.ensure_db(args.db, args.dir, taxonomy))
    log_rows, warnings = aplib.read_log_a(args.log, taxonomy)
    for w in warnings:
        output_fn(f"警告: {w}")
    pend = pending_path(args.log)
    if args.resume or pend.exists():
        if not pend.exists():
            output_fn("続きの答え合わせはありません")
            return 1
        if not args.resume:
            output_fn(f"答え合わせが途中の通しがあります（{pend.name}）。先に `--day {args.day} --resume` で終えてください")
            return 1
        pending = load_pending(pend, pool)
        output_fn(f"中断した答え合わせを再開します：残り {len(pending)}問")
        s = Session(pool, log_rows, args.log, input_fn=input_fn, output_fn=output_fn, clock=clock,
                    day=int(pending[0]["row"]["日目"]), kind="通し", quota=len(pending))
        s.grade(pending)
        s.summary()
        return 0
    kind = "復習" if args.review else "通し" if args.exam else "弱点" if args.weak else "分野別"
    if args.review:
        mains, outside = review_mains(pool, log_rows, args.day, args.all)
        for x in outside:
            output_fn(f"問題バンク外の解き直し：{x['出典']} 問{x['問番号']}（{x['コード']}）→ 解いたら add_log.py で種別＝復習として記録")
    else:
        mids = [f"{int(m):02d}" for m in args.mid.split(",")] if args.mid else None
        if not args.source and not args.use_reserved:
            reserved = load_reserved()
            pool = drill_pool(pool, reserved)
            if reserved:
                output_fn(f"通し用に取っておく回（{len(reserved)}回）は使いません：{'、'.join(reserved)}")
        mains = select_mains(pool, log_rows, taxonomy, mids=mids, source=args.source,
                             weak=args.weak, include_seen=args.include_seen)
    if not mains:
        output_fn("条件に合う問題がありません" + ("" if args.review else "（--include-seen で既出も対象にできます）"))
        return 1
    quota = args.count or (len(mains) if args.exam or args.review else default_quota(analyze_A.load_plan(), args.day))
    output_fn(f"AP 科目A {args.day}日目（{kind}）：候補 {len(mains)}問、上限 {quota}問。q で中断")
    Session(pool, log_rows, args.log, input_fn=input_fn, output_fn=output_fn, clock=clock,
            day=args.day, kind=kind, quota=quota, related=not args.no_related, sheet=args.sheet).run(mains)
    return 0


if __name__ == "__main__":
    sys.exit(main())
