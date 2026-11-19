import assert from "node:assert/strict";
import { test } from "node:test";
import { capability, gradeOf, GRADES } from "../src/capability.ts";
import { close, S, unwrap, unwrapErr } from "./helpers.ts";

// [9,10,11]: 平均 10, 標本標準偏差 1
const xs = S(9, 10, 11);

test("両側規格 (中心一致): Cp = Cpk = 12/6 = 2", () => {
  const c = unwrap(capability(xs, { kind: "two-sided", lsl: 4, usl: 16 }));
  close(c.cp, 2);
  close(c.cpk, 2);
});

test("両側規格 (偏りあり): Cp=9/6=1.5, Cpu=6/3=2, Cpl=3/3=1, Cpk=1", () => {
  const c = unwrap(capability(xs, { kind: "two-sided", lsl: 7, usl: 16 }));
  close(c.cp, 1.5);
  close(c.cpu, 2);
  close(c.cpl, 1);
  close(c.cpk, 1);
});

test("平均が規格外なら Cpk は負", () => {
  const c = unwrap(capability(xs, { kind: "two-sided", lsl: 11.5, usl: 20 }));
  close(c.cpk, -0.5);
});

test("上側規格のみ: Cpk = Cpu、cp は存在しない", () => {
  const c = unwrap(capability(xs, { kind: "upper", usl: 13 }));
  close(c.cpk, 1);
  close(c.cpu, 1);
  assert.equal("cp" in c, false);
});

test("下側規格のみ: Cpk = Cpl", () => {
  const c = unwrap(capability(xs, { kind: "lower", lsl: 4 }));
  close(c.cpk, 2);
  close(c.cpl, 2);
});

test("ばらつき 0 はエラー (0 除算で Infinity を返さない)", () => {
  const r = capability(S(5, 5, 5), { kind: "upper", usl: 6 });
  assert.deepEqual(unwrapErr(r), { kind: "zero-variance" });
});

test("LSL >= USL はエラー", () => {
  for (const [lsl, usl] of [[5, 5], [6, 5], [Number.NaN, 5]] as const) {
    const e = unwrapErr(capability(xs, { kind: "two-sided", lsl, usl }));
    assert.equal(e.kind, "invalid-spec");
  }
});

test("gradeOf: 境界値", () => {
  const g = (v: number) => gradeOf(v).grade;
  assert.equal(g(2), "A");
  assert.equal(g(1.67), "A");
  assert.equal(g(1.669), "B");
  assert.equal(g(1.33), "B");
  assert.equal(g(1.329), "C");
  assert.equal(g(1.0), "C");
  assert.equal(g(0.999), "D");
  assert.equal(g(-3), "D");
  assert.equal(g(Number.NaN), "D");
});

test("GRADES: しきい値は降順 (find の前提)", () => {
  for (let i = 1; i < GRADES.length; i++) {
    assert.ok(GRADES[i - 1]!.min > GRADES[i]!.min);
  }
});

test("型を無視した呼び出し (JavaScript 側など) は実行時にも止まる", () => {
  assert.throws(() => capability(xs, { kind: "both" } as never), /想定外/);
});
