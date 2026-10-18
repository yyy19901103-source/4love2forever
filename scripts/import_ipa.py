"""IPA の AP 午前（科目A）の過去問 PDF を問題バンクに取り込む。

問題冊子は画像だけの PDF なので、tesseract で OCR する。冊子の数字の「0」は中に点のある字形で、
日本語モデルは「9」と読み違えやすい。そこで英語モデルでも読み、同じ位置の単語の数字の桁数が
一致するときは英語モデルの数字を使う。解答例 PDF は文字データから正解を読む。
小分類コードは、解答例の分野（T/M/S）の範囲でシラバスの用語と照合して推定する（code_basis に記録）。

使い方:
  python scripts/import_ipa.py QS.pdf ANS.pdf --exam 2025r07a [--out data/questions/ipa_2025r07a.jsonl]
  --exam は IPA のファイル名の先頭（例 2025r07a＝令和7年度秋期、2025r07h＝令和7年度春期）。
必要なもの: pdfimages・pdftotext（poppler-utils）、tesseract と日本語データ（tesseract-ocr-jpn）。
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import aplib
import syllabus

LABELS = ("ア", "イ", "ウ", "エ")
FIELD_MIDS = {"T": range(1, 14), "M": range(14, 17), "S": range(17, 24)}
FIGURE_WORDS = ("図", "表", "グラフ", "カルノー", "次のとおり", "次の流れ", "次の条件", "次の手順", "次の式", "次の関係")
# OCR でよく起きる読み誤り（行頭の問番号・選択肢の記号）
LINE_FIXES = [
    (re.compile(r"^[間閑門問]\W{0,2}([0-9０-９]{1,2})"), r"問\1 "),
    (re.compile(r"^([アイウエ])\1(?=\s)"), r"\1"),            # 「エエ」→「エ」
    (re.compile(r"^7(?=\s)"), "ア"),                          # 「ア」を 7 と読む
    (re.compile(r"^工(?=\s)"), "エ"),                         # 「エ」を漢字の工と読む
    (re.compile(r"^[ーｰ-](?=\s)"), "イ"),
]


def exam_label(exam: str) -> str:
    """2025r07a → 令和7年度秋期。"""
    m = re.fullmatch(r"(\d{4})r(\d{2})([ah])", exam)
    if not m:
        raise ValueError(f"--exam は 2025r07a のような形式です: {exam!r}")
    return f"令和{int(m.group(2))}年度{'秋期' if m.group(3) == 'a' else '春期'}"


def ap_siken_url(exam: str, number: int) -> str:
    """過去問道場の問題ページ（URL の形式は 27_aki/q78.html の実例に合わせた。令和の年度表記は未確認）。"""
    m = re.fullmatch(r"\d{4}r(\d{2})([ah])", exam)
    return f"https://www.ap-siken.com/kakomon/{m.group(1)}_{'aki' if m.group(2) == 'a' else 'haru'}/q{number}.html"


def ipa_year_url(exam: str) -> str:
    m = re.fullmatch(r"(\d{4})r(\d{2})[ah]", exam)
    return f"https://www.ipa.go.jp/shiken/mondai-kaiotu/{m.group(1)}r{m.group(2)}.html"


def parse_answers(text: str) -> dict[int, tuple[str, str]]:
    """解答例のテキストから {問番号: (正解, 分野T/M/S)}。"""
    text = unicodedata.normalize("NFKC", text)
    found = {int(n): (a, f) for n, a, f in re.findall(r"問\s*(\d{1,2})\s+([アイウエ])\s+([TMS])", text)}
    return dict(sorted(found.items()))


def _tsv_words(img: Path, lang: str, env) -> list[dict]:
    out = subprocess.run(["tesseract", str(img), "-", "-l", lang, "--psm", "6", "tsv"],
                         capture_output=True, text=True, env=env, timeout=300).stdout
    words = []
    for r in csv.DictReader(io.StringIO(out), delimiter="\t", quoting=csv.QUOTE_NONE):
        if r.get("level") == "5" and (r.get("text") or "").strip():
            x, y, w, h = (int(r[k]) for k in ("left", "top", "width", "height"))
            words.append({"line": (r["block_num"], r["par_num"], r["line_num"]),
                          "box": (x, y, x + w, y + h), "text": r["text"]})
    return words


def fix_digits(jpn: list[dict], eng: list[dict]) -> int:
    """日本語モデルの単語の数字を、同じ位置の英語モデルの数字で置き換える（桁数が同じときだけ）。"""
    changed = 0
    for w in jpn:
        jd = re.findall(r"\d", w["text"])
        if not jd:
            continue
        x0, y0, x1, y1 = w["box"]
        near = sorted((e for e in eng
                       if x0 - 4 <= (e["box"][0] + e["box"][2]) / 2 <= x1 + 4
                       and y0 - 4 <= (e["box"][1] + e["box"][3]) / 2 <= y1 + 4), key=lambda e: e["box"][0])
        ed = [c for e in near for c in re.findall(r"\d", e["text"])]
        if len(ed) == len(jd) and ed != jd:
            it = iter(ed)
            w["text"] = re.sub(r"\d", lambda _: next(it), w["text"])
            changed += 1
    return changed


def ocr_pages(qs_pdf: Path, workdir: Path) -> tuple[list[str], int]:
    """ページごとのテキストと、数字を直した単語の数を返す。"""
    subprocess.run(["pdfimages", "-j", str(qs_pdf), str(workdir / "p")], check=True)
    images = sorted(workdir.glob("p-*.jpg"))
    env = dict(os.environ, OMP_THREAD_LIMIT="1")  # 1プロセス1スレッドにしないと並列時に極端に遅くなる

    def run(img: Path) -> tuple[str, int]:
        jpn, eng = _tsv_words(img, "jpn", env), _tsv_words(img, "eng", env)
        changed = fix_digits(jpn, eng)
        lines: dict = {}
        for w in jpn:
            lines.setdefault(w["line"], []).append(w["text"])
        return "\n".join(" ".join(ws) for ws in lines.values()), changed

    with ThreadPoolExecutor(max_workers=os.cpu_count() or 2) as pool:
        results = list(pool.map(run, images))
    return [t for t, _ in results], sum(c for _, c in results)


def clean_line(line: str) -> str:
    line = unicodedata.normalize("NFKC", line).strip()
    line = line.replace("“", "\"").replace("”", "\"")
    for pat, rep in LINE_FIXES:
        line = pat.sub(rep, line)
    # 日本語の文字どうしの間に入った空白（OCR の単語区切り）を取り除く。
    # ただし単独の ア〜エ（選択肢の記号）の前後の空白は残す。
    parts = re.split(r"((?:^|(?<=\s))[アイウエ](?=\s|$))", line)
    joined = []
    for part in parts:
        if part in LABELS:
            joined.append(f" {part} ")
        else:
            part = re.sub(r"(?<=[^\x00-\x7f])\s+(?=[^\x00-\x7f])", "", part)
            joined.append(re.sub(r"(?<=[^\x00-\x7f])\s+(?=[,.%)])|(?<=[(])\s+(?=[^\x00-\x7f])", "", part))
    return re.sub(r"\s+", " ", "".join(joined)).strip()


def join_lines(lines: list[str]) -> str:
    """折り返しで分かれた行をつなぐ（日本語の間は空白なし、英数字の間は空白1つ）。"""
    out = ""
    for ln in lines:
        if not ln:
            continue
        if out and re.match(r"[A-Za-z0-9]", out[-1]) and re.match(r"[A-Za-z0-9]", ln[0]):
            out += " "
        out += ln
    return re.sub(r"\s+", " ", out).strip()


def number_variants(ocr: str) -> set[str]:
    """0 を 9 と読む誤りを考えた、問番号の候補。"""
    variants = {ocr, ocr.replace("9", "0")}
    variants |= {ocr[:i] + "0" + ocr[i + 1:] for i, c in enumerate(ocr) if c == "9"}
    return variants


def split_questions(pages: list[str], expected: int = 80) -> dict[int, dict]:
    """ページのテキストを問ごとに分ける。

    「問＋数字」の行を見出しの候補とし、番号は前後関係で確定する。
    - 直前の問の選択肢を エ まで読んでいれば次の問とみなし、番号は直前＋1（読み取った番号が＋2なら見出し1つの読み落とし）。
    - エ まで読んでいなければ（選択肢が図の中にある問など）、読み取った番号が＋1か＋2のときだけ見出しとみなす。
    """
    questions: dict[int, dict] = {}
    current, seen_last_choice = 0, True
    for page_no, text in enumerate(pages, start=1):
        for raw in text.splitlines():
            line = clean_line(re.sub(r"^[|\[\]!'`.:;,_\s]+", "", raw))
            if re.fullmatch(r"\W*\d+\W*", line) and len(line) <= 8:  # ページ番号
                continue
            m = re.match(r"^問\s*(\d{1,2})\s*(.*)$", line)
            n = None
            if m:
                variants = number_variants(m.group(1))
                if str(current + 1) in variants:
                    n = current + 1
                elif str(current + 2) in variants:
                    n = current + 2
                elif seen_last_choice:
                    n = current + 1
            if n and n <= expected:
                current, seen_last_choice = n, False
                questions[n] = {"page": page_no, "lines": [m.group(2)]}
            elif current:
                questions[current]["lines"].append(line)
                if re.match(r"^エ\s", line) or re.search(r"\sエ\s", line):
                    seen_last_choice = True
    return questions


def parse_choices(lines: list[str]) -> tuple[str, dict[str, str]]:
    """本文と選択肢に分ける。選択肢は行頭の ア〜エ、または1行に並んだ「ア 33 イ 50 …」。"""
    stem, choices, cur = [], {}, None
    for ln in lines:
        inline = re.findall(r"(?:^|\s)([アイウエ])\s+(.+?)(?=\s+[アイウエ]\s|$)", ln)
        labels = [lb for lb, _ in inline]
        if ln[:1] in LABELS and len(inline) >= 2 and labels == sorted(labels, key=LABELS.index):
            for lb, body in inline:
                choices[lb] = [body]
            cur = labels[-1]
        elif ln[:1] in LABELS and re.match(r"^[アイウエ](\s|$)", ln) and (cur is None or LABELS.index(ln[0]) > LABELS.index(cur)):
            cur = ln[0]
            choices[cur] = [ln[1:].strip()]
        elif cur:
            choices[cur].append(ln)
        else:
            stem.append(ln)
        # 行末に記号だけが残り、本文が次の行にある場合（「ウ 172.30.123.0 エ」→ 次の行が エ の本文）
        tail = re.search(r"\s([アイウエ])$", ln)
        if tail and cur and LABELS.index(tail.group(1)) > LABELS.index(cur):
            if choices.get(cur) and choices[cur][-1].endswith(tail.group(0)):
                choices[cur][-1] = choices[cur][-1][: -len(tail.group(0))]
            cur = tail.group(1)
            choices[cur] = []
    return join_lines(stem), {k: tidy_choice(join_lines(v)) for k, v in choices.items()}


def tidy_choice(text: str) -> str:
    """選択肢の末尾に付いたページ番号などの残骸を取り除く。"""
    text = re.sub(r"\s*[ー一\-–―]+\s*\d{1,2}\s*[ー一\-–―]+.*$", "", text)  # 「ー 7 ーー」
    text = re.sub(r"[\s|」「『』_]+$", "", text)
    m = re.match(r"^([\d,.%]+)\s*(.{1,8})$", text)
    if m and re.search(r"[|」「『』ァィゥェォ]|^[ー一イ\s]{1,3}$", m.group(2)):  # 数値の後ろの明らかな残骸
        text = m.group(1)
    return text.strip()


_TERM_INDEX: dict | None = None


def term_index(smalls: dict, notes: dict) -> dict[str, set[str]]:
    """照合語 → その語を持つ小分類コードの集合（シラバスの項目名・用語例と、学習項目の名前から作る）。"""
    global _TERM_INDEX
    if _TERM_INDEX is None:
        index: dict[str, set[str]] = {}
        for code, small in smalls.items():
            for item in small["items"]:
                for term in [item["name"], *syllabus.item_terms(item)]:
                    for k in syllabus.keywords(term):
                        if len(k) >= 2:
                            index.setdefault(k, set()).add(code)
            for name, _ in notes.get(code, []):
                for k in syllabus.keywords(name):
                    if len(k) >= 2:
                        index.setdefault(k, set()).add(code)
        _TERM_INDEX = index
    return _TERM_INDEX


def guess_code(text: str, field: str, smalls: dict, notes: dict) -> tuple[str, list[str]]:
    """分野（T/M/S）の範囲で、問題文に現れる照合語の重みの合計が最大の小分類を選ぶ。

    重み = 語の長さ ÷ その語を持つ小分類の数。「データ」「管理」のようにどこにでも出る語は軽く、
    「ロールフォワード」のように特定の小分類にしか出ない長い語は重くなる。
    """
    allowed = {c for c in smalls if int(c[:2]) in FIELD_MIDS[field]}
    norm = syllabus.norm(text)
    scores: dict[str, float] = {}
    hits: dict[str, list[str]] = {}
    for k, codes in term_index(smalls, notes).items():
        if k in norm:
            for code in codes & allowed:
                scores[code] = scores.get(code, 0) + len(k) / len(codes)
                hits.setdefault(code, []).append(k)
    if not scores:
        return sorted(allowed)[0], []
    best = max(sorted(scores), key=lambda c: scores[c])
    return best, sorted(hits[best], key=len, reverse=True)


def build(qs_pdf: Path, ans_pdf: Path, exam: str) -> tuple[list[dict], list[str]]:
    label = exam_label(exam)
    answers = parse_answers(subprocess.run(["pdftotext", "-layout", str(ans_pdf), "-"],
                                           capture_output=True, text=True, check=True).stdout)
    cache = Path(tempfile.gettempdir()) / f"ap_ocr_{exam}_{qs_pdf.stat().st_size}.json"
    if cache.exists():
        pages, digit_fixes = json.loads(cache.read_text(encoding="utf-8"))
    else:
        with tempfile.TemporaryDirectory() as tmp:
            pages, digit_fixes = ocr_pages(qs_pdf, Path(tmp))
        cache.write_text(json.dumps([pages, digit_fixes], ensure_ascii=False), encoding="utf-8")
    blocks = split_questions(pages)
    smalls = syllabus.small_categories(syllabus.load_syllabus())
    notes = syllabus.load_notes()
    out, problems = [], []
    if len(answers) != 80:
        problems.append(f"解答例から読めた正解が {len(answers)} 問（80問のはず）")
    for n in range(1, 81):
        if n not in blocks:
            problems.append(f"問{n}: 問題冊子から見出しを見つけられません")
            continue
        stem, choices = parse_choices(blocks[n]["lines"])
        missing = [lb for lb in LABELS if not choices.get(lb)]
        figure = any(w in stem for w in FIGURE_WORDS) or bool(missing)
        for lb in missing:  # 図の中に選択肢があるなど、文字で取れなかったもの
            choices[lb] = "（原本の図・表を参照）"
        answer, field = answers.get(n, (None, "T"))
        if answer is None:
            problems.append(f"問{n}: 正解が解答例にありません")
            continue
        numeric = sum(bool(re.fullmatch(r"[\d,.%\s]+", v)) for v in choices.values()) >= 2
        notes_ = ["OCRで取り込み。記号・数式は原本で確認"]
        if numeric:
            notes_.insert(0, "数値の選択肢あり：0と9の読み違いの可能性があるため数値は原本で確認")
        code, hits = guess_code(stem + " " + " ".join(choices.values()), field, smalls, notes)
        out.append({
            "id": f"AP-{exam.upper()}-{n:02d}", "origin": "IPA過去問",
            "source": f"{label} AP 午前 問{n}（原本 p.{blocks[n]['page']}）",
            "code": code, "stem": stem or "（原本を参照）", "choices": choices, "answer": answer,
            "explanation": "", "explanation_author": "", "keywords": hits[:8],
            "links": [{"site": "IPA 過去問題", "url": ipa_year_url(exam)},
                      {"site": "過去問道場（解説）", "url": ap_siken_url(exam, n)}],
            "has_figure": figure, "field": field, "page": blocks[n]["page"],
            "code_basis": "推定（シラバス用語との一致：" + ("、".join(hits[:5]) or "一致なし") + "）",
            "note": "。".join(notes_) + f"（原本 p.{blocks[n]['page']}）",
        })
        if missing:
            problems.append(f"問{n}: 選択肢 {''.join(missing)} を文字で取れませんでした（図表として扱う）")
    problems.insert(0, f"数字を英語モデルで直した単語：{digit_fixes}件")
    return out, problems


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("qs", type=Path)
    p.add_argument("ans", type=Path)
    p.add_argument("--exam", required=True)
    p.add_argument("--out", type=Path)
    args = p.parse_args(argv)
    questions, problems = build(args.qs, args.ans, args.exam)
    out = args.out or aplib.DATA_DIR / "questions" / f"ipa_{args.exam}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for q in questions:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    figures = sum(q["has_figure"] for q in questions)
    print(f"{exam_label(args.exam)}: {len(questions)}問を {out} に書きました（図表あり {figures}問）")
    for msg in problems:
        print(f"  ! {msg}")
    return 0 if len(questions) == 80 else 1


if __name__ == "__main__":
    sys.exit(main())
