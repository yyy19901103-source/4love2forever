import assert from "node:assert/strict";
import type { Result } from "../src/result.ts";
import { toSamples, type Samples } from "../src/samples.ts";

export function unwrap<T, E>(r: Result<T, E>): T {
  if (!r.ok) assert.fail(`失敗しました: ${JSON.stringify(r.error)}`);
  return r.value;
}
export function unwrapErr<T, E>(r: Result<T, E>): E {
  if (r.ok) assert.fail("成功してしまいました");
  return r.error;
}
export const S = (...v: number[]): Samples => unwrap(toSamples(v));
export const close = (actual: number, expected: number, eps = 1e-9): void =>
  assert.ok(Math.abs(actual - expected) < eps, `${actual} ≠ ${expected}`);
