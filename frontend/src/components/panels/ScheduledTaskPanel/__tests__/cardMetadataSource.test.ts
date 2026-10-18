import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
const source = readFileSync(new URL("../index.tsx", import.meta.url), "utf8");

test("execution mode and conversation link use compact card metadata typography", () => {
  expect(source).toMatch(
    /<span className="skill-meta-pill">\s*\{t\(\s*task.execution_mode/,
  );
  expect(source).toMatch(/className="skill-meta-pill hover:text-theme-text"/);
});

test("task models use configured brand icons instead of a generic chip", () => {
  expect(source).toMatch(/<ModelIconImg/);
  expect(source).toMatch(/icon=\{model\.icon\}/);
  expect(source).not.toMatch(/<Cpu/);
});
