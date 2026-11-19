/**
 * 型のテスト。実行はされず、`tsc --noEmit` が検査する。
 * `@ts-expect-error` は「次の行がコンパイルエラーになること」を要求する指示で、
 * もしエラーにならなくなったら (= 型の守りが壊れたら) tsc 自体が失敗する。
 */
import { capability, gradeOf, type Grade, type Spec } from "../src/capability.ts";
import { describeError } from "../src/cli.ts";
import { groupBy } from "../src/parse.ts";
import { mean, toSamples, type Samples } from "../src/samples.ts";

type Equal<A, B> = (<T>() => T extends A ? 1 : 2) extends <T>() => T extends B ? 1 : 2 ? true : false;
const expectTrue = <T extends true>(): T | void => undefined;

declare const xs: Samples;

// ブランド型: 未検証の配列は統計関数に渡せない
// @ts-expect-error number[] は Samples ではない
mean([1, 2, 3]);

// Result: ok を確認する前は value を読めない
const r = toSamples([1, 2]);
// @ts-expect-error 失敗の可能性が残っている
r.value;
if (r.ok) mean(r.value);

// 判別可能ユニオン: 種類と項目の組み合わせ違い・未知の種類は書けない
// @ts-expect-error upper に lsl は無い
const bad1: Spec = { kind: "upper", lsl: 1 };
// @ts-expect-error 未知の kind
const bad2: Spec = { kind: "both", lsl: 1, usl: 2 };
void bad1, bad2;

// 条件付き型: 規格の種類で結果の形が決まる
const two = capability(xs, { kind: "two-sided", lsl: 0, usl: 1 });
const upper = capability(xs, { kind: "upper", usl: 1 });
if (two.ok && upper.ok) {
  expectTrue<Equal<typeof two.value.cp, number>>();
  // @ts-expect-error 片側規格に Cp は無い
  upper.value.cp;
  // @ts-expect-error readonly なので書き換え不可
  two.value.cp = 0;
}

// as const: 表から型が生成される
expectTrue<Equal<Grade, "A" | "B" | "C" | "D">>();
// @ts-expect-error "E" という等級は表に無い
const g: Grade = "E";
void g, gradeOf;

// 網羅性: 未知のエラー種類は渡せない
// @ts-expect-error
describeError({ kind: "unknown" });

// ジェネリクス: キーと要素の型が結果に引き継がれる
const grouped = groupBy([{ line: "A", v: 1 }], (row) => row.line);
expectTrue<Equal<typeof grouped, Map<string, { line: string; v: number }[]>>>();
