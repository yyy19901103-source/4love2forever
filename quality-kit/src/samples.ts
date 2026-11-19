import { err, ok, type Result } from "./result.ts";

/**
 * 特徴3: ブランド型 (branded type)
 * 中身はただの number[] だが、検証済みの配列だけに「印」を付けて区別する。
 * 統計関数は Samples しか受け取らないので、未検証データを渡すとコンパイルエラーになる。
 * 印は型の上だけに存在し、実行時のコストはゼロ。
 */
declare const samplesBrand: unique symbol;
export type Samples = readonly number[] & { readonly [samplesBrand]: true };

export type SampleError =
  | { readonly kind: "too-few"; readonly count: number }
  | { readonly kind: "not-finite"; readonly index: number };

/** 検証の入口。2 点以上・全て有限値 (NaN と ±Infinity を除く) の場合だけ Samples を返す。 */
export function toSamples(values: readonly number[]): Result<Samples, SampleError> {
  if (values.length < 2) return err({ kind: "too-few", count: values.length });
  const bad = values.findIndex((v) => !Number.isFinite(v));
  if (bad !== -1) return err({ kind: "not-finite", index: bad });
  return ok(values as Samples);
}

export function mean(xs: Samples): number {
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

/** 標本標準偏差 (n-1 で割る) */
export function sampleStd(xs: Samples): number {
  const m = mean(xs);
  const ss = xs.reduce((a, x) => a + (x - m) ** 2, 0);
  return Math.sqrt(ss / (xs.length - 1));
}

/** 中央値。空配列は呼び出し側の誤りなので NaN を返す。 */
export function median(values: readonly number[]): number {
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  const hi = s[mid];
  if (hi === undefined) return Number.NaN;
  // noUncheckedIndexedAccess: 配列アクセスは undefined の可能性ありと扱われる
  const lo = s[mid - 1];
  return s.length % 2 === 1 || lo === undefined ? hi : (lo + hi) / 2;
}
