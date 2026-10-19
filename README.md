# Mermaid スケジュール最適化プロトタイプ

Mermaid コード（flowchart / gantt）から、以下を自動生成する最小アプリです。

- フローチャート再構成
- 依存関係 + 並列数制約を考慮した最適化ガントチャート
- プロジェクト総期間

## できること

1. Mermaid の矢印 (`A --> B`) から依存関係を抽出
2. Mermaid gantt 風タスク定義を読み取り
3. 最大並列実行数 (`--max-parallel`) の制約付きでスケジュール最適化
4. Mermaid の gantt と flowchart を出力

## 入力フォーマット（例）

```mermaid
flowchart TD
    A --> B
    A --> C
    B --> D
    C --> D

gantt
    title Sample
    section Dev
    要件定義 :A, 2d
    設計 :B, after A, 3d
    実装 :C, after A, 5d
    テスト :D, after B, 2d
```

> `after` がなくても、flowchart の依存関係で補完されます（task_id が一致する場合）。

## ローカル実行方法

```bash
python mermaid_scheduler.py sample.mmd --start-date 2026-04-01 --max-parallel 2
```

JSON 出力:

```bash
python mermaid_scheduler.py sample.mmd --json
```

## GitHub でそのまま実行できる？

できます。`push` / `pull_request` のたびに GitHub Actions で以下を自動実行します。

1. `pytest` によるユニットテスト
2. CLI のスモークテスト（JSON 出力）

ワークフロー定義: `.github/workflows/ci.yml`

### 正式公開（リリース）後の運用案

- `main` へのマージ必須チェックとして `CI` を required status check に設定
- タグ（例: `v1.0.0`）でリリース運用
- 失敗時はマージブロックして品質担保

## 今後の拡張アイデア

- クリティカルパス可視化
- リソース（担当者、工数）最適化
- Web UI（Streamlit / FastAPI + フロント）
- Mermaid live preview 連携

---

# 応用情報技術者試験（AP）学習ログ

方針・日程・ルールは `CLAUDE.md` を参照。日付ではなく「日目」で管理する（科目A 1〜17日目、科目B B1〜B26）。

| ファイル | 役割 |
| --- | --- |
| `data/taxonomy.csv` | 科目A体系表（23中分類・96小分類、コード例 `09-3`） |
| `data/plan_A.csv` | 科目Aの17日計画（日目・問題数・種別・内容、合計900問） |
| `scripts/add_log.py` | 1問ずつ対話形式で `data/log_A.csv` に追記（入力時に検証。分析は誤答と確信度B/Cだけ） |
| `scripts/quiz.py` | 演習：問題バンクから出題し、日目・種別・初見を付けて自動記録 |
| `scripts/review_queue.py` | その日の最初の15分で解き直す問題（前日・3日前の誤答と確信度C） |
| `scripts/pass_prob.py` | 初見の通し直近2回の平均から合格確率（推定）を出す |
| `scripts/analyze_A.py` | 科目A日次レポート（中分類別Wilson 95%区間・上位3中分類・優先度と2〜6日目の組み替え案・判定ゲート・原因別・計画差） |
| `scripts/analyze_B.py` | 科目B分野別レポートと選択分野の入れ替え判定（6割未満） |
| `docs/error_log.md` | 誤りの記録 |
| `docs/taxonomy_tree.md` / `scripts/tree_A.py` | 科目Aの知識体系ツリー |
| `data/questions/*.jsonl` / `scripts/qbank.py` | 問題バンクの正本と SQLite の作成・検証・収録状況 |
| `docs/sources.md` | 問題の出典と利用条件 |
| `data/syllabus_A.json` / `data/scope_B.json` / `docs/ap_knowledge_tree.html` | シラバス Ver.7.2・試験要綱 Ver.5.6 から抽出した公式の知識ツリー（ユーザー提示） |
| `data/reserved_exams.txt` | 通し演習（初見）のために取っておく回。分野別・弱点演習と関連問題には使わない |
| `scripts/import_ipa.py` | IPA の AP 午前 PDF（問題冊子・解答例）を OCR して問題バンクに取り込む |
| `scripts/syllabus.py` | シラバスとの照合（`check`）・学習ノート生成（`book`）・ツリー表示（`tree`） |
| `docs/ap_syllabus_book.md` | シラバスの並びで、425項目すべての用語例と要点をまとめた学習ノート |
| `data/knowledge_items.csv` / `data/syllabus_points.csv` | 要点の正本（学習項目433件＋シラバス項目に直接付けた198件） |

1日の流れ（例：2日目）：

```bash
python scripts/review_queue.py --day 2                       # 最初の15分で解き直す一覧
python scripts/quiz.py --day 2 --review                      # 問題バンクにある分を解き直す（種別＝復習）
python scripts/quiz.py --day 2 --mid 11 --count 40           # 分野別（記録は自動）
python scripts/add_log.py                                    # 過去問道場など他で解いた1問を手入力
python scripts/analyze_A.py --day 2 --out reports/A_day02.md # 日次レポート
```

その他：

```bash
python scripts/quiz.py --day 1 --source 令和7年度秋期 --exam     # 通し（途中で正誤を見せない）
python scripts/quiz.py --day 7 --weak 3                        # 誤答数上位3中分類
python scripts/pass_prob.py                                    # 合格確率（ログの初見の通しから）
python scripts/pass_prob.py --mean 52                          # 平均を指定して計算
python scripts/qbank.py stats                                  # 問題バンクの収録状況
python scripts/analyze_B.py --from B1 --to B7                  # 科目Bの選択確定（B1〜B7）
python -m pytest -q                                            # テスト
```
