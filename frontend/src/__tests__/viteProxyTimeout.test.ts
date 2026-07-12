import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const viteConfigSource = readFileSync(
  resolve(import.meta.dirname, "../../vite.config.ts"),
  "utf8",
);

test("vite dev proxy keeps only chat streams open for 24 hours", () => {
  expect(viteConfigSource).toMatch(
    /\^\/api\/chat\/sessions\/\[\^\/\]\+\/stream\$[\s\S]*timeout: 86400000,/,
  );
  expect(viteConfigSource).toMatch(/"\/api": \{[\s\S]*timeout: 300000,/);
});
