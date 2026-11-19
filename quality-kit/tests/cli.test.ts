import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { test } from "node:test";
import { describeError, main, type AppError, type GroupReport } from "../src/cli.ts";

const CSV = "group,value\nA,9\nA,10\nA,11\nB,9\nB,10\nB,11\nB,10\n";

function run(args: string[], files: Record<string, string> = { "d.csv": CSV }) {
  const out: string[] = [];
  const err: string[] = [];
  const code = main(args, {
    readFile: (p) => {
      const t = files[p];
      if (t === undefined) throw new Error(`ENOENT: ${p}`);
      return t;
    },
    out: (l) => out.push(l),
    err: (l) => err.push(l),
  });
  return { code, out, err: err.join("\n") };
}

test("JSON 出力: グループ別に計算される", () => {
  const r = run(["d.csv", "--lsl", "4", "--usl", "16", "--json"]);
  assert.equal(r.code, 0);
  const reports = JSON.parse(r.out.join("\n")) as GroupReport[];
  assert.deepEqual(reports.map((x) => [x.group, x.n]), [["A", 3], ["B", 4]]);
  const a = reports[0]!;
  assert.deepEqual([a.mean, a.sigma, a.cp, a.cpk, a.grade, a.outliers], [10, 1, 2, 2, "A", 0]);
});

test("表出力: 見出し + グループ数ぶんの行", () => {
  const r = run(["d.csv", "--lsl", "4", "--usl", "16"]);
  assert.equal(r.out.length, 3);
  assert.equal(r.out[1], "A\t3\t10.000\t1.000\t2.000\t2.000\tA\t0");
});

test("片側規格: Cp は '-' / null", () => {
  const up = run(["d.csv", "--usl", "13"]);
  assert.equal(up.out[1], "A\t3\t10.000\t1.000\t-\t1.000\tC\t0");
  const lo = run(["d.csv", "--lsl", "7", "--json"]);
  assert.equal((JSON.parse(lo.out.join("\n")) as GroupReport[])[0]!.cp, null);
});

test("使い方の誤りは終了コード 2", () => {
  for (const args of [[], ["d.csv"], ["a.csv", "b.csv", "--usl", "1"], ["d.csv", "--usl", "abc"], ["d.csv", "--lsl", "x"], ["d.csv", "--bogus"]]) {
    const r = run(args);
    assert.equal(r.code, 2, args.join(" "));
    assert.match(r.err, /使い方の誤り/);
    assert.deepEqual(r.out, []);
  }
});

test("データの問題は終了コード 1 と原因メッセージ", () => {
  const cases: [string, string[], RegExp][] = [
    ["", ["--usl", "1"], /ファイルを読めません/],
    ["x,y\n", ["--usl", "1"], /1 行目は/],
    ["group,value\nA,zz\n", ["--usl", "1"], /2 行目を読めません/],
    ["group,value\n", ["--usl", "1"], /データ行がありません/],
    ["group,value\nA,1\n", ["--usl", "1"], /\[A\]\n.*1 点しか/],
    ["group,value\nA,1\nA,1\n", ["--usl", "1"], /\[A\]\n.*ばらつきが 0/],
    ["group,value\nA,1\nA,2\n", ["--lsl", "5", "--usl", "1"], /規格が不正/],
  ];
  for (const [csv, opts, pattern] of cases) {
    const r = run(["f.csv", ...opts], csv === "" ? {} : { "f.csv": csv });
    assert.equal(r.code, 1, csv);
    assert.match(r.err, pattern);
  }
});

test("describeError: 全種類が空でない日本語になる", () => {
  const all: AppError[] = [
    { kind: "usage", message: "m" },
    { kind: "io", message: "m" },
    { kind: "bad-header", found: "h" },
    { kind: "bad-row", line: 2, text: "t" },
    { kind: "empty" },
    { kind: "too-few", count: 1 },
    { kind: "not-finite", index: 0 },
    { kind: "zero-variance" },
    { kind: "invalid-spec", lsl: 2, usl: 1 },
  ];
  const messages = all.map(describeError);
  assert.equal(new Set(messages).size, all.length);
  assert.match(describeError({ kind: "not-finite", index: 0 }), /1 番目/);
  assert.throws(() => describeError({ kind: "unknown" } as never), /想定外/);
});

test("結合テスト: 実プロセスとして起動 (サンプル CSV)", () => {
  const bin = new URL("../src/bin.ts", import.meta.url).pathname;
  const csv = new URL("../sample/measurements.csv", import.meta.url).pathname;
  const okRun = spawnSync(process.execPath, [bin, csv, "--lsl", "9.9", "--usl", "10.1", "--json"], { encoding: "utf8" });
  assert.equal(okRun.status, 0, okRun.stderr);
  const reports = JSON.parse(okRun.stdout) as GroupReport[];
  assert.deepEqual(reports.map((r) => [r.group, r.grade, r.outliers]), [["LineA", "A", 0], ["LineB", "D", 1]]);

  const ng = spawnSync(process.execPath, [bin, "no-such-file.csv", "--usl", "1"], { encoding: "utf8" });
  assert.equal(ng.status, 1);
  assert.match(ng.stderr, /ファイルを読めません/);
  assert.equal(ng.stdout, "");
});
