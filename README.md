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

方針・日程・ルールは `CLAUDE.md` を参照。

| ファイル | 役割 |
| --- | --- |
| `data/taxonomy.csv` | 科目A体系表（23中分類・96小分類、コード例 `09-3`） |
| `data/plan_A.csv` | 科目Aの日別計画問題数（10/19〜11/8、合計1080問） |
| `scripts/add_log.py` | 1問ずつ対話形式で `data/log_A.csv` に追記（入力時に検証） |
| `scripts/analyze_A.py` | 科目A日次レポート（中分類別Wilson 95%区間・上位3中分類・原因別・計画差） |
| `scripts/analyze_B.py` | 科目B分野別レポートと選択分野の入れ替え判定（6割未満） |
| `docs/error_log.md` | 誤りの記録 |
| `docs/taxonomy_tree.md` / `scripts/tree_A.py` | 科目Aの知識体系ツリー |
| `data/questions/*.jsonl` / `scripts/qbank.py` | 問題バンクの正本と SQLite の作成・検証・収録状況 |
| `scripts/quiz.py` | 演習：誤答・不明 → 解説と解析 → 関連問題を2〜3問 → 次の本問 |
| `docs/sources.md` | 問題の出典と利用条件 |

```bash
python scripts/quiz.py --mid 09                             # 中分類09を演習（記録は自動）
python scripts/quiz.py --source 令和6年度秋期 --exam          # 通し演習
python scripts/quiz.py --weak 3                             # 誤答数上位3中分類（翌朝30分）
python scripts/qbank.py stats                               # 問題バンクの収録状況
python scripts/add_log.py                                   # 紙・他サイトで解いた1問を手入力で記録
python scripts/analyze_A.py                                 # 最新日付の日次レポート
python scripts/analyze_A.py --date 2026-10-19 --out reports/A_2026-10-19.md
python scripts/analyze_B.py --since 2026-11-10 --until 2026-11-16
python -m pytest -q                                         # テスト
```
