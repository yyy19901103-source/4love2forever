import { readFileSync } from "node:fs";
import { main } from "./cli.ts";

process.exitCode = main(process.argv.slice(2), {
  readFile: (path) => readFileSync(path, "utf8"),
  out: (line) => console.log(line),
  err: (line) => console.error(line),
});
