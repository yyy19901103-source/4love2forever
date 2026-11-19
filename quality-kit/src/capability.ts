import { assertNever, err, ok, type Result } from "./result.ts";
import { mean, sampleStd, type Samples } from "./samples.ts";

/** 規格の種類。kind で判別する。 */
export type Spec =
  | { readonly kind: "two-sided"; readonly lsl: number; readonly usl: number }
  | { readonly kind: "upper"; readonly usl: number }
  | { readonly kind: "lower"; readonly lsl: number };

/**
 * 特徴4: 条件付き型 (conditional type)
 * 規格の種類に応じて戻り値の形が変わる。
 * 片側規格には Cp が定義されないため、片側規格の結果から `.cp` を読むとコンパイルエラーになる。
 */
export type Capability<S extends Spec> = S extends { kind: "two-sided" }
  ? { readonly cp: number; readonly cpu: number; readonly cpl: number; readonly cpk: number }
  : S extends { kind: "upper" }
    ? { readonly cpu: number; readonly cpk: number }
    : { readonly cpl: number; readonly cpk: number };

export type CapabilityError =
  | { readonly kind: "zero-variance" }
  | { readonly kind: "invalid-spec"; readonly lsl: number; readonly usl: number };

/**
 * 工程能力指数。
 *   Cp  = (USL - LSL) / (6σ)
 *   Cpu = (USL - μ) / (3σ),  Cpl = (μ - LSL) / (3σ)
 *   Cpk = min(Cpu, Cpl)  (片側規格では存在する側のみ)
 * σ は標本標準偏差。
 */
export function capability<S extends Spec>(
  xs: Samples,
  spec: S,
): Result<Capability<S>, CapabilityError> {
  const mu = mean(xs);
  const sigma = sampleStd(xs);
  if (sigma === 0) return err({ kind: "zero-variance" });
  const s: Spec = spec;
  let out: Capability<Spec>;
  switch (s.kind) {
    case "two-sided": {
      if (!(s.lsl < s.usl)) return err({ kind: "invalid-spec", lsl: s.lsl, usl: s.usl });
      const cpu = (s.usl - mu) / (3 * sigma);
      const cpl = (mu - s.lsl) / (3 * sigma);
      out = { cp: (s.usl - s.lsl) / (6 * sigma), cpu, cpl, cpk: Math.min(cpu, cpl) };
      break;
    }
    case "upper": {
      const cpu = (s.usl - mu) / (3 * sigma);
      out = { cpu, cpk: cpu };
      break;
    }
    case "lower": {
      const cpl = (mu - s.lsl) / (3 * sigma);
      out = { cpl, cpk: cpl };
      break;
    }
    default:
      return assertNever(s);
  }
  // 条件付き型の戻り値は実装側で証明できないため、ここ 1 か所だけ型アサーションを使う
  return ok(out as Capability<S>);
}

/**
 * 特徴5: `as const` + `satisfies`
 * 表をそのまま型にする。Grade 型 ("A" | "B" | "C" | "D") は下の表から自動生成されるので、
 * 表と型がずれない。しきい値は一般的な目安であり、社内基準に合わせて差し替える前提。
 */
export const GRADES = [
  { grade: "A", min: 1.67, label: "十分" },
  { grade: "B", min: 1.33, label: "適正" },
  { grade: "C", min: 1.0, label: "要注意" },
  { grade: "D", min: Number.NEGATIVE_INFINITY, label: "不足" },
] as const satisfies readonly { grade: string; min: number; label: string }[];

export type GradeRule = (typeof GRADES)[number];
export type Grade = GradeRule["grade"];

export function gradeOf(cpk: number): GradeRule {
  return GRADES.find((g) => cpk >= g.min) ?? GRADES[3];
}
