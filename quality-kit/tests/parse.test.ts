import assert from "node:assert/strict";
import { test } from "node:test";
import { groupBy, parseCsv } from "../src/parse.ts";
import { unwrap, unwrapErr } from "./helpers.ts";

test("parseCsv: 正常系 (CRLF・空行・前後の空白・BOM・大文字ヘッダー)", () => {
  const rows = unwrap(parseCsv("﻿Group,Value\r\nA, 1.5\r\n\r\n B ,-2e-1\r\n"));
  assert.deepEqual(rows, [
    { group: "A", value: 1.5 },
    { group: "B", value: -0.2 },
  ]);
});

test("parseCsv: ヘッダー違い・空文字", () => {
  assert.deepEqual(unwrapErr(parseCsv("name,value\nA,1")), { kind: "bad-header", found: "name,value" });
  assert.equal(unwrapErr(parseCsv("")).kind, "bad-header");
});

test("parseCsv: 不正な行は行番号付きで報告", () => {
  const bad = (body: string) => unwrapErr(parseCsv(`group,value\nA,1\n${body}`));
  assert.deepEqual(bad("A,abc"), { kind: "bad-row", line: 3, text: "A,abc" });
  assert.equal(bad("A").kind, "bad-row");
  assert.equal(bad("A,").kind, "bad-row"); // Number("") は 0 になるため明示的に拒否
  assert.equal(bad("A, ").kind, "bad-row");
  assert.equal(bad(",1").kind, "bad-row");
  assert.equal(bad("A,1,2").kind, "bad-row");
  assert.equal(bad("A,Infinity").kind, "bad-row");
});

test("parseCsv: データ行なし", () => {
  assert.deepEqual(unwrapErr(parseCsv("group,value\n\n")), { kind: "empty" });
});

test("groupBy: 出現順を保ってまとめる", () => {
  const m = groupBy([1, 2, 3, 4, 5], (n) => (n % 2 === 0 ? "even" : "odd"));
  assert.deepEqual([...m], [["odd", [1, 3, 5]], ["even", [2, 4]]]);
  assert.equal(groupBy([], (x) => x).size, 0);
});
