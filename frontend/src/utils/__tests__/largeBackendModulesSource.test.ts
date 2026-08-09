import { readFileSync } from "node:fs";
import { relative, resolve } from "node:path";

import { glob } from "glob";

const LINE_THRESHOLD = 1000;
const projectRoot = resolve(import.meta.dirname, "../../../..");

test("backend source files stay within the 1000 line limit", async () => {
  const files = await glob("**/*.py", {
    cwd: resolve(projectRoot, "src"),
    absolute: true,
  });

  const oversized = files
    .map((file) => ({
      file: relative(projectRoot, file),
      lines: readFileSync(file, "utf8").split("\n").length,
    }))
    .filter(({ lines }) => lines > LINE_THRESHOLD)
    .sort((left, right) => left.file.localeCompare(right.file));

  expect(oversized).toEqual([]);
});
