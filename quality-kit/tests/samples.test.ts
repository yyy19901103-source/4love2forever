import assert from "node:assert/strict";
import { test } from "node:test";
import { assertNever } from "../src/result.ts";
import { mean, median, sampleStd, toSamples } from "../src/samples.ts";
import { close, S, unwrapErr } from "./helpers.ts";

test("toSamples: 2 点未満は拒否", () => {
  assert.deepEqual(unwrapErr(toSamples([])), { kind: "too-few", count: 0 });
  assert.deepEqual(unwrapErr(toSamples([1])), { kind: "too-few", count: 1 });
});

test("toSamples: NaN / Infinity は位置付きで拒否", () => {
  assert.deepEqual(unwrapErr(toSamples([1, Number.NaN, 3])), { kind: "not-finite", index: 1 });
  assert.deepEqual(unwrapErr(toSamples([1, 2, Infinity])), { kind: "not-finite", index: 2 });
});

test("mean / sampleStd: 手計算と一致", () => {
  // [1,2,3,4,5]: 平均 3, 偏差平方和 10, 不偏分散 10/4 = 2.5
  const xs = S(1, 2, 3, 4, 5);
  close(mean(xs), 3);
  close(sampleStd(xs), Math.sqrt(2.5));
  // [2,4,4,4,5,5,7,9]: 平均 5, 偏差平方和 32, 不偏分散 32/7
  close(sampleStd(S(2, 4, 4, 4, 5, 5, 7, 9)), Math.sqrt(32 / 7));
});

test("median: 奇数個・偶数個・未ソート・空", () => {
  assert.equal(median([3, 1, 2]), 2);
  assert.equal(median([4, 1, 3, 2]), 2.5);
  assert.equal(median([7]), 7);
  assert.ok(Number.isNaN(median([])));
});

test("median: 入力配列を書き換えない", () => {
  const v = [3, 1, 2];
  median(v);
  assert.deepEqual(v, [3, 1, 2]);
});

test("assertNever: 実行時に到達したら例外", () => {
  assert.throws(() => assertNever("x" as never), /想定外/);
});
