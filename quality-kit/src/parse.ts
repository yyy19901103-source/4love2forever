import { err, ok, type Result } from "./result.ts";

export interface Row {
  readonly group: string;
  readonly value: number;
}

export type ParseError =
  | { readonly kind: "bad-header"; readonly found: string }
  | { readonly kind: "bad-row"; readonly line: number; readonly text: string }
  | { readonly kind: "empty" };

/** `group,value` 形式の CSV を読む。外部入力は実行時に検証してから型を付ける。 */
export function parseCsv(text: string): Result<Row[], ParseError> {
  // split は必ず 1 要素以上を返すので、その事実をタプル型で表す
  const lines = text.split(/\r?\n/).map((l) => l.trim()) as [string, ...string[]];
  const header = lines[0];
  if (header.replace(/^﻿/, "").toLowerCase() !== "group,value") {
    return err({ kind: "bad-header", found: header });
  }
  const rows: Row[] = [];
  for (const [i, line] of lines.entries()) {
    if (i === 0 || line === "") continue;
    const cells = line.split(",");
    const [group, raw] = cells;
    const value = Number(raw);
    if (cells.length !== 2 || !group || !raw?.trim() || !Number.isFinite(value)) {
      return err({ kind: "bad-row", line: i + 1, text: line });
    }
    rows.push({ group: group.trim(), value });
  }
  return rows.length === 0 ? err({ kind: "empty" }) : ok(rows);
}

/**
 * 特徴6: ジェネリクス (generics)
 * どんな型の配列でも使える。キーの型 K と要素の型 T は呼び出し側から推論され、
 * 結果の Map<K, T[]> にそのまま引き継がれる (any に崩れない)。
 */
export function groupBy<T, K>(items: readonly T[], keyOf: (item: T) => K): Map<K, T[]> {
  const map = new Map<K, T[]>();
  for (const item of items) {
    const key = keyOf(item);
    const bucket = map.get(key);
    if (bucket) bucket.push(item);
    else map.set(key, [item]);
  }
  return map;
}
