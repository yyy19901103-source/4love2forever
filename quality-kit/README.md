# quality-kit

TypeScript（タイプスクリプト：型付きの JavaScript）の特徴を示すための品質統計ツールです。
CSV（表形式データ）を読み、グループ別に Cp / Cpk・等級・外れ値数を出力します。
EWMA・CUSUM・Hampel はライブラリ関数として使えます。

## 実行

Node.js 22.18 以上が必要です（`.ts` をビルドなしで直接実行します）。

```bash
npm ci
```

```bash
npm test
```

```bash
node src/bin.ts sample/measurements.csv --lsl 9.9 --usl 10.1
```

出力例:

```
group	n	mean	sigma	Cp	Cpk	grade	outliers
LineA	8	10.000	0.013	2.546	2.546	A	0
LineB	8	10.050	0.151	0.221	0.110	D	1
```

`--json` を付けると JSON で出力します。`--lsl` か `--usl` の片方だけなら片側規格として扱い、Cp は `-` になります。
終了コードは 0（正常）／1（データの問題）／2（使い方の誤り）です。

## このコードで分かる TypeScript の特徴

| # | 特徴 | 何が防げるか | 場所 |
|---|---|---|---|
| 1 | 判別可能ユニオン `Result<T, E>` | エラー処理の書き忘れ（`ok` を確認しないと値を読めない） | `src/result.ts` |
| 2 | 網羅性チェック `assertNever` | エラー種類を追加したのにメッセージを書き忘れる | `src/cli.ts` の `describeError` |
| 3 | ブランド型 `Samples` | 未検証データ（NaN 入り、1 点だけ）を統計関数に渡す | `src/samples.ts` |
| 4 | 条件付き型 `Capability<S>` | 片側規格の結果から存在しない Cp を読む | `src/capability.ts` |
| 5 | `as const` + `satisfies` | 等級表と等級の型がずれる | `src/capability.ts` の `GRADES` |
| 6 | ジェネリクス `groupBy<T, K>` | 汎用関数を通すと型情報が消える | `src/parse.ts` |

これらはすべてコンパイル時だけの仕組みで、実行時のコストはありません。
一方、ファイルなど外部からの入力は型では守れないため、`parseCsv` と `toSamples` が実行時に検証します。

## テストの構成

| 種類 | 内容 | ファイル |
|---|---|---|
| 型検査 | `strict` に加え `noUncheckedIndexedAccess` などを有効化 | `tsconfig.json` |
| 型のテスト | 「コンパイルエラーになるべきコード」が本当にエラーになるか | `tests/types.check.ts` |
| 単体テスト | 手計算した期待値との照合、境界値、不正入力 | `tests/*.test.ts` |
| CLI テスト | 引数・出力・終了コード（入出力を差し替えて検証） | `tests/cli.test.ts` |
| 結合テスト | 実プロセスとして起動しサンプル CSV を処理 | `tests/cli.test.ts` の最後 |
| カバレッジ | `src/` の行・分岐・関数が 100% 未満なら失敗（起動用の `src/bin.ts` は結合テストで確認） | `package.json` |

## 計算式

- Cp = (USL − LSL) / 6σ、Cpk = min((USL − μ) / 3σ, (μ − LSL) / 3σ)。σ は標本標準偏差（n − 1 で割る）
- EWMA: z_i = λx_i + (1 − λ)z_{i−1}、管理限界 = 目標値 ± Lσ√(λ/(2 − λ)·(1 − (1 − λ)^{2i}))
- CUSUM: C⁺_i = max(0, x_i − (目標値 + K) + C⁺_{i−1})、C⁻ も対称。K = kσ、H = hσ
- Hampel: |x_i − 窓内中央値| > しきい値 × 1.4826 × MAD なら外れ値

等級のしきい値（1.67 / 1.33 / 1.00）は一般的な目安です。社内基準がある場合は `GRADES` を差し替えてください。
