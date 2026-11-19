import assert from "node:assert/strict";
import { test } from "node:test";
import { cusum, ewma, hampel, hampelDefault, MAD_SCALE } from "../src/charts.ts";
import { close, S, unwrap, unwrapErr } from "./helpers.ts";

test("EWMA: z と管理限界が手計算と一致 (λ=0.5, σ=1, L=3)", () => {
  const p = unwrap(ewma(S(1, 1), { target: 0, sigma: 1, lambda: 0.5 }));
  // z1 = 0.5·1 + 0.5·0 = 0.5,  z2 = 0.5·1 + 0.5·0.5 = 0.75
  close(p[0]!.z, 0.5);
  close(p[1]!.z, 0.75);
  // 幅1 = 3·sqrt(0.5/1.5·(1-0.5^2)) = 3·sqrt(0.25) = 1.5
  close(p[0]!.ucl, 1.5);
  close(p[0]!.lcl, -1.5);
  // 幅2 = 3·sqrt(1/3·(1-0.5^4)) = 3·sqrt(0.3125)
  close(p[1]!.ucl, 3 * Math.sqrt(0.3125));
  assert.equal(p.some((q) => q.signal), false);
});

test("EWMA: λ=1 はシューハート管理図と同じ (z = x, 幅 = Lσ)", () => {
  const p = unwrap(ewma(S(0.5, -2, 3.1), { target: 0, sigma: 1, lambda: 1 }));
  assert.deepEqual(p.map((q) => q.z), [0.5, -2, 3.1]);
  for (const q of p) close(q.ucl, 3);
  assert.deepEqual(p.map((q) => q.signal), [false, false, true]);
});

test("EWMA: 持続的なずれ 1.5σ を 5 点目で検出 (上側・下側)", () => {
  // λ=0.2, L=3: z_i = 1.5(1-0.8^i)、幅_i = sqrt(1-0.8^(2i))
  //   i=4: z=0.8856 < 幅=0.9123 → 未検出   i=5: z=1.0085 > 幅=0.9448 → 検出
  const first = (v: number) =>
    unwrap(ewma(S(...Array<number>(10).fill(v)), { target: 0, sigma: 1 })).findIndex((q) => q.signal);
  assert.equal(first(1.5), 4);
  assert.equal(first(-1.5), 4);
});

test("EWMA: ずれ 1σ ちょうどは z が限界に漸近するだけで検出されない", () => {
  const p = unwrap(ewma(S(...Array<number>(200).fill(1)), { target: 0, sigma: 1 }));
  assert.equal(p.some((q) => q.signal), false);
});

test("EWMA: 不正なオプション", () => {
  const xs = S(1, 2);
  const opt = (o: object) => unwrapErr(ewma(xs, { target: 0, sigma: 1, ...o })).option;
  assert.equal(opt({ sigma: 0 }), "sigma");
  assert.equal(opt({ sigma: Number.NaN }), "sigma");
  assert.equal(opt({ lambda: 0 }), "lambda");
  assert.equal(opt({ lambda: 1.01 }), "lambda");
  assert.equal(opt({ L: -1 }), "L");
});

test("CUSUM: 上側の累積が手計算と一致 (k=0.5, h=2)", () => {
  const p = unwrap(cusum(S(1, 1, 1, 1, 1), { target: 0, sigma: 1, h: 2 }));
  // C+ = 0.5, 1.0, 1.5, 2.0, 2.5  → H=2 を超えるのは 5 点目のみ
  assert.deepEqual(p.map((q) => q.cPlus), [0.5, 1, 1.5, 2, 2.5]);
  assert.deepEqual(p.map((q) => q.signal), ["none", "none", "none", "none", "upper"]);
  assert.ok(p.every((q) => q.cMinus === 0));
});

test("CUSUM: 下側は対称", () => {
  const p = unwrap(cusum(S(-1, -1, -1, -1, -1), { target: 0, sigma: 1, h: 2 }));
  assert.deepEqual(p.map((q) => q.cMinus), [0.5, 1, 1.5, 2, 2.5]);
  assert.equal(p.at(-1)!.signal, "lower");
});

test("CUSUM: 目標値どおりなら累積しない / 0 でリセットされる", () => {
  const p = unwrap(cusum(S(1, -3, 0, 0), { target: 0, sigma: 1 }));
  assert.deepEqual(p.map((q) => q.cPlus), [0.5, 0, 0, 0]);
  assert.deepEqual(p.map((q) => q.cMinus), [0, 2.5, 2, 1.5]);
});

test("CUSUM: 不正なオプション", () => {
  const xs = S(1, 2);
  const opt = (o: object) => unwrapErr(cusum(xs, { target: 0, sigma: 1, ...o })).option;
  assert.equal(opt({ sigma: -1 }), "sigma");
  assert.equal(opt({ k: 0 }), "k");
  assert.equal(opt({ h: Infinity }), "h");
});

test("Hampel: スパイクを 1 点だけ検出 (手計算)", () => {
  const p = unwrap(hampel(S(1, 2, 3, 4, 50, 6, 7)));
  // 5 点目の窓 = [2,3,4,50,6,7] → 中央値 5、|偏差| = [3,2,1,45,1,2] → MAD 2
  close(p[4]!.median, 5);
  close(p[4]!.scaledMad, 2 * MAD_SCALE);
  assert.deepEqual(p.filter((q) => q.outlier).map((q) => q.index), [4]);
});

test("Hampel: MAD = 0 でも中央値と異なる点だけを検出", () => {
  const p = unwrap(hampel(S(1, 1, 1, 1, 100, 1, 1, 1, 1)));
  assert.deepEqual(p.filter((q) => q.outlier).map((q) => q.index), [4]);
});

test("Hampel: 外れ値なし・窓幅の指定", () => {
  assert.equal(unwrap(hampel(S(1, 2, 3, 4, 5))).some((q) => q.outlier), false);
  const p = unwrap(hampel(S(1, 2, 30, 4, 5), { halfWindow: 1, threshold: 3 }));
  // 3 点目の窓 = [2,30,4] → 中央値 4、MAD 2
  close(p[2]!.median, 4);
  assert.equal(p[2]!.outlier, true);
});

test("Hampel: 不正なオプション", () => {
  const xs = S(1, 2);
  const opt = (o: object) => unwrapErr(hampel(xs, o)).option;
  assert.equal(opt({ halfWindow: 0 }), "halfWindow");
  assert.equal(opt({ halfWindow: 1.5 }), "halfWindow");
  assert.equal(opt({ threshold: 0 }), "threshold");
});

test("hampelDefault: オプション省略時の hampel と同じ結果", () => {
  const xs = S(1, 2, 3, 4, 50, 6, 7);
  assert.deepEqual(hampelDefault(xs), unwrap(hampel(xs)));
});
