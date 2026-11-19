import { parseArgs } from "node:util";
import { capability, gradeOf, type CapabilityError, type Grade, type Spec } from "./capability.ts";
import { hampelDefault } from "./charts.ts";
import { groupBy, parseCsv, type ParseError } from "./parse.ts";
import { assertNever } from "./result.ts";
import { mean, sampleStd, toSamples, type SampleError } from "./samples.ts";

export type AppError =
  | ParseError
  | SampleError
  | CapabilityError
  | { readonly kind: "usage"; readonly message: string }
  | { readonly kind: "io"; readonly message: string };

/**
 * 全エラーを日本語に変換する。
 * AppError に種類を追加してここに case を書き忘れると、assertNever の行がコンパイルエラーになる。
 */
export function describeError(e: AppError): string {
  switch (e.kind) {
    case "usage":
      return `使い方の誤り: ${e.message}`;
    case "io":
      return `ファイルを読めません: ${e.message}`;
    case "bad-header":
      return `1 行目は "group,value" にしてください (実際: "${e.found}")`;
    case "bad-row":
      return `${e.line} 行目を読めません: "${e.text}"`;
    case "empty":
      return "データ行がありません";
    case "too-few":
      return `データが ${e.count} 点しかありません (2 点以上必要)`;
    case "not-finite":
      return `${e.index + 1} 番目の値が数値ではありません`;
    case "zero-variance":
      return "ばらつきが 0 のため工程能力を計算できません";
    case "invalid-spec":
      return `規格が不正です (LSL=${e.lsl} は USL=${e.usl} より小さくしてください)`;
    default:
      return assertNever(e);
  }
}

export interface GroupReport {
  readonly group: string;
  readonly n: number;
  readonly mean: number;
  readonly sigma: number;
  readonly cp: number | null;
  readonly cpk: number;
  readonly grade: Grade;
  readonly outliers: number;
}

export interface Io {
  readonly readFile: (path: string) => string;
  readonly out: (line: string) => void;
  readonly err: (line: string) => void;
}

const USAGE = "quality-kit <file.csv> [--lsl 数値] [--usl 数値] [--json]";

function toSpec(lsl: string | undefined, usl: string | undefined): Spec | undefined {
  const lo = lsl === undefined ? undefined : Number(lsl);
  const hi = usl === undefined ? undefined : Number(usl);
  if (Number.isNaN(lo) || Number.isNaN(hi)) return undefined;
  if (lo !== undefined && hi !== undefined) return { kind: "two-sided", lsl: lo, usl: hi };
  if (hi !== undefined) return { kind: "upper", usl: hi };
  if (lo !== undefined) return { kind: "lower", lsl: lo };
  return undefined;
}

/** CLI 本体。終了コードを返す (0: 正常, 1: データの問題, 2: 使い方の誤り)。 */
export function main(argv: readonly string[], io: Io): number {
  const fail = (e: AppError, code: number): number => {
    io.err(describeError(e));
    return code;
  };

  let parsed;
  try {
    parsed = parseArgs({
      args: [...argv],
      allowPositionals: true,
      options: { lsl: { type: "string" }, usl: { type: "string" }, json: { type: "boolean" } },
    });
  } catch (e) {
    return fail({ kind: "usage", message: `${(e as Error).message}\n${USAGE}` }, 2);
  }
  const file = parsed.positionals[0];
  const spec = toSpec(parsed.values.lsl, parsed.values.usl);
  if (!file || parsed.positionals.length !== 1 || !spec) {
    return fail({ kind: "usage", message: `ファイル 1 つと --lsl / --usl の少なくとも一方が必要です\n${USAGE}` }, 2);
  }

  let text: string;
  try {
    text = io.readFile(file);
  } catch (e) {
    return fail({ kind: "io", message: (e as Error).message }, 1);
  }

  const rows = parseCsv(text);
  if (!rows.ok) return fail(rows.error, 1);

  const reports: GroupReport[] = [];
  for (const [group, items] of groupBy(rows.value, (r) => r.group)) {
    const xs = toSamples(items.map((r) => r.value));
    if (!xs.ok) {
      io.err(`[${group}]`);
      return fail(xs.error, 1);
    }
    const cap = capability(xs.value, spec);
    if (!cap.ok) {
      io.err(`[${group}]`);
      return fail(cap.error, 1);
    }
    reports.push({
      group,
      n: xs.value.length,
      mean: mean(xs.value),
      sigma: sampleStd(xs.value),
      // `in` による絞り込み: 両側規格のときだけ cp が存在する
      cp: "cp" in cap.value ? cap.value.cp : null,
      cpk: cap.value.cpk,
      grade: gradeOf(cap.value.cpk).grade,
      outliers: hampelDefault(xs.value).filter((p) => p.outlier).length,
    });
  }

  if (parsed.values.json) {
    io.out(JSON.stringify(reports, null, 2));
    return 0;
  }
  io.out("group\tn\tmean\tsigma\tCp\tCpk\tgrade\toutliers");
  for (const r of reports) {
    const f = (v: number | null): string => (v === null ? "-" : v.toFixed(3));
    io.out([r.group, r.n, f(r.mean), f(r.sigma), f(r.cp), f(r.cpk), r.grade, r.outliers].join("\t"));
  }
  return 0;
}
