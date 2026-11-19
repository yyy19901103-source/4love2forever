import { err, ok, type Result } from "./result.ts";
import { median, type Samples } from "./samples.ts";

export type ChartError = {
  readonly kind: "invalid-option";
  readonly option: string;
  readonly value: number;
};

const positive = (option: string, value: number): ChartError | undefined =>
  Number.isFinite(value) && value > 0 ? undefined : { kind: "invalid-option", option, value };

export interface EwmaOptions {
  readonly target: number;
  readonly sigma: number;
  /** 平滑化係数 0 < λ <= 1 (既定 0.2) */
  readonly lambda?: number;
  /** 管理限界の幅 (既定 3) */
  readonly L?: number;
}
export interface EwmaPoint {
  readonly index: number;
  readonly value: number;
  readonly z: number;
  readonly lcl: number;
  readonly ucl: number;
  readonly signal: boolean;
}

/**
 * EWMA 管理図。
 *   z_i = λ x_i + (1-λ) z_{i-1},  z_0 = 目標値
 *   管理限界 = 目標値 ± L σ sqrt( λ/(2-λ) · (1 - (1-λ)^(2i)) )   (i は 1 始まり)
 */
export function ewma(xs: Samples, opts: EwmaOptions): Result<EwmaPoint[], ChartError> {
  const { target, sigma, lambda = 0.2, L = 3 } = opts;
  const bad = positive("sigma", sigma) ?? positive("lambda", lambda) ?? positive("L", L);
  if (bad) return err(bad);
  if (lambda > 1) return err({ kind: "invalid-option", option: "lambda", value: lambda });
  let z = target;
  return ok(
    xs.map((value, index) => {
      z = lambda * value + (1 - lambda) * z;
      const width =
        L * sigma * Math.sqrt((lambda / (2 - lambda)) * (1 - (1 - lambda) ** (2 * (index + 1))));
      const lcl = target - width;
      const ucl = target + width;
      return { index, value, z, lcl, ucl, signal: z > ucl || z < lcl };
    }),
  );
}

export interface CusumOptions {
  readonly target: number;
  readonly sigma: number;
  /** 参照値 K = kσ (既定 0.5) */
  readonly k?: number;
  /** 決定区間 H = hσ (既定 5) */
  readonly h?: number;
}
export interface CusumPoint {
  readonly index: number;
  readonly value: number;
  readonly cPlus: number;
  readonly cMinus: number;
  readonly signal: "upper" | "lower" | "none";
}

/**
 * 表形式 CUSUM。
 *   C+_i = max(0, x_i - (目標値 + K) + C+_{i-1})
 *   C-_i = max(0, (目標値 - K) - x_i + C-_{i-1})
 *   C+ > H なら上側、C- > H なら下側の異常
 */
export function cusum(xs: Samples, opts: CusumOptions): Result<CusumPoint[], ChartError> {
  const { target, sigma, k = 0.5, h = 5 } = opts;
  const bad = positive("sigma", sigma) ?? positive("k", k) ?? positive("h", h);
  if (bad) return err(bad);
  const K = k * sigma;
  const H = h * sigma;
  let cPlus = 0;
  let cMinus = 0;
  return ok(
    xs.map((value, index) => {
      cPlus = Math.max(0, value - (target + K) + cPlus);
      cMinus = Math.max(0, target - K - value + cMinus);
      const signal = cPlus > H ? "upper" : cMinus > H ? "lower" : "none";
      return { index, value, cPlus, cMinus, signal };
    }),
  );
}

export interface HampelOptions {
  /** 片側の窓幅 (既定 3 → 最大 7 点) */
  readonly halfWindow?: number;
  /** 判定しきい値 (既定 3) */
  readonly threshold?: number;
}
export interface HampelPoint {
  readonly index: number;
  readonly value: number;
  readonly median: number;
  readonly scaledMad: number;
  readonly outlier: boolean;
}

/** 正規分布のとき MAD を σ の推定値に換算する係数 */
export const MAD_SCALE = 1.4826;

/**
 * Hampel フィルタ (外れ値検出)。
 *   窓内の中央値 m と MAD を求め、|x_i - m| > threshold × 1.4826 × MAD なら外れ値。
 *   端では窓を切り詰める。
 */
export function hampel(xs: Samples, opts: HampelOptions = {}): Result<HampelPoint[], ChartError> {
  const { halfWindow = 3, threshold = 3 } = opts;
  const bad = positive("halfWindow", halfWindow) ?? positive("threshold", threshold);
  if (bad) return err(bad);
  if (!Number.isInteger(halfWindow)) {
    return err({ kind: "invalid-option", option: "halfWindow", value: halfWindow });
  }
  return ok(scan(xs, halfWindow, threshold));
}

/** 既定値 (片側 3 点・しきい値 3) での Hampel。オプションが無いので失敗しない。 */
export function hampelDefault(xs: Samples): HampelPoint[] {
  return scan(xs, 3, 3);
}

function scan(xs: Samples, halfWindow: number, threshold: number): HampelPoint[] {
  return xs.map((value, index) => {
    const win = xs.slice(Math.max(0, index - halfWindow), index + halfWindow + 1);
    const m = median(win);
    const scaledMad = MAD_SCALE * median(win.map((v) => Math.abs(v - m)));
    return { index, value, median: m, scaledMad, outlier: Math.abs(value - m) > threshold * scaledMad };
  });
}
