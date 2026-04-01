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
