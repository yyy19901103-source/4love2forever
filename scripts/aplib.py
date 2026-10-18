"""応用情報技術者試験 学習ログ用の共通処理（体系表・ログ列・検証）。"""
from __future__ import annotations

import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
TAXONOMY_PATH = DATA_DIR / "taxonomy.csv"
LOG_A_PATH = DATA_DIR / "log_A.csv"
LOG_B_PATH = DATA_DIR / "log_B.csv"
PLAN_A_PATH = DATA_DIR / "plan_A.csv"

# Excel で開いても文字化けしないよう BOM 付き UTF-8 で書き、読むときは BOM の有無を問わない
ENCODING = "utf-8-sig"

LOG_A_REQUIRED = [
    "日付", "出典", "問番号", "コード", "確信度", "正誤", "原因",
    "正解の根拠", "誤選択肢が違う理由", "解答秒", "分析秒",
]
# 問題ID（問題バンクの id、手入力なら空）と種別（本問／関連）は末尾に追加した任意列。
# 列のない古いログは 問題ID=空・種別=本問 として読む。
LOG_A_OPTIONAL = {"問題ID": "", "種別": "本問"}
LOG_A_COLUMNS = LOG_A_REQUIRED + list(LOG_A_OPTIONAL)
KINDS = ("本問", "関連")
LOG_B_COLUMNS = [
    "日付", "出典", "問番号", "分野", "得点率", "所要分",
    "失点した設問", "原因", "書けなかった根拠の位置",
]

CONFIDENCE = {"A": "確信", "B": "半々", "C": "勘"}
CORRECTNESS = ("正", "誤")
CAUSES = ("知識不足", "混同", "計算ミス", "読み違い", "時間切れ")

# 科目B の11分野（問1は必須、問2〜11から4問選択）。分野名の表記は IPA 一次情報で未確認、
# 問番号との対応も IPA 非公表（未確認）。そのため一覧外の分野名は弾かず警告にとどめる。
B_FIELDS = (
    "情報セキュリティ", "経営戦略", "プログラミング", "システムアーキテクチャ",
    "ネットワーク", "データベース", "組込みシステム開発", "情報システム開発",
    "プロジェクトマネジメント", "サービスマネジメント", "システム監査",
)
B_REQUIRED_FIELD = "情報セキュリティ"


def load_taxonomy(path: Path = TAXONOMY_PATH) -> dict[str, dict[str, str]]:
    """コード（例 09-3）→ 行 の辞書を返す。"""
    with open(path, encoding=ENCODING, newline="") as f:
        return {row["コード"]: row for row in csv.DictReader(f)}


def middle_categories(taxonomy: dict[str, dict[str, str]]) -> dict[str, str]:
    """中分類番号 → 中分類名（番号順）。"""
    mids = {row["中分類番号"]: row["中分類"] for row in taxonomy.values()}
    return dict(sorted(mids.items()))


def is_effective_wrong(row: dict[str, str]) -> bool:
    """誤答、または確信度Cの正解（実質誤答）なら True。"""
    return row["正誤"] == "誤" or row["確信度"] == "C"


def validate_row_a(row: dict[str, str], taxonomy: dict[str, dict[str, str]]) -> list[str]:
    """科目Aログ1行を検証し、エラーメッセージの一覧を返す（空なら正常）。"""
    from datetime import date

    errors = []
    missing = [c for c in LOG_A_REQUIRED if c not in row]
    if missing:
        return [f"列が不足しています: {missing}"]
    if (row.get("種別") or "本問") not in KINDS:
        errors.append(f"種別は 本問/関連 のいずれかです: {row['種別']!r}")
    try:
        date.fromisoformat(row["日付"])
    except ValueError:
        errors.append(f"日付は YYYY-MM-DD 形式にしてください: {row['日付']!r}")
    for col in ("出典", "問番号"):
        if not row[col].strip():
            errors.append(f"{col}が空です")
    if row["コード"] not in taxonomy:
        errors.append(f"コード {row['コード']!r} は taxonomy.csv にありません")
    if row["確信度"] not in CONFIDENCE:
        errors.append(f"確信度は A/B/C のいずれかです: {row['確信度']!r}")
    if row["正誤"] not in CORRECTNESS:
        errors.append(f"正誤は 正/誤 のいずれかです: {row['正誤']!r}")
    if row["確信度"] in CONFIDENCE and row["正誤"] in CORRECTNESS:
        if is_effective_wrong(row):
            if row["原因"] not in CAUSES:
                errors.append(f"誤答・実質誤答には原因を1つ付けてください（{'/'.join(CAUSES)}）: {row['原因']!r}")
        elif row["原因"]:
            errors.append("確信度A/Bの正解には原因を付けません")
    for col in ("解答秒", "分析秒"):
        v = row[col]
        if not v.isdigit():
            errors.append(f"{col}は0以上の整数（秒）です: {v!r}")
    return errors


def read_log_a(path: Path, taxonomy: dict[str, dict[str, str]]) -> tuple[list[dict[str, str]], list[str]]:
    """ログを読み、(正常行, 不正行の警告) を返す。ファイルがなければ空。"""
    if not path.exists():
        return [], []
    rows, warnings = [], []
    with open(path, encoding=ENCODING, newline="") as f:
        for lineno, row in enumerate(csv.DictReader(f), start=2):
            for col, default in LOG_A_OPTIONAL.items():
                row[col] = row.get(col) or default
            errs = validate_row_a(row, taxonomy)
            if errs:
                warnings.append(f"{path.name} {lineno}行目を除外: {'; '.join(errs)}")
            else:
                rows.append(row)
    return rows, warnings


def append_row(path: Path, columns: list[str], row: dict[str, str]) -> None:
    """ヘッダがなければ付けて1行追記する。"""
    new_file = not path.exists() or path.stat().st_size == 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding=ENCODING, newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        if new_file:
            w.writeheader()
        w.writerow({c: row.get(c, "") for c in columns})


def wilson_interval(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """二項比率 k/n の Wilson スコア信頼区間（既定は95%）。n=0 なら (0, 1)。"""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z / denom * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, center - half), min(1.0, center + half)
