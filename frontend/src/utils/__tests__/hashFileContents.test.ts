import { createHash } from "node:crypto";
import { expect, test } from "vitest";
import { hashFileContents } from "../hashFileContents";

test("hashes across chunk boundaries without reading the whole video into memory", async () => {
  const bytes = new Uint8Array(5 * 1024 * 1024 + 17);
  for (let i = 0; i < bytes.length; i++) bytes[i] = i % 251;
  const file = new Blob([bytes]);
  file.arrayBuffer = async () => {
    throw new Error("whole file read");
  };
  expect(await hashFileContents(file)).toBe(
    createHash("sha256").update(bytes).digest("hex"),
  );
});

test("desktop CSP permits the hashing wasm without allowing string evaluation", async () => {
  const { readFileSync } = await import("node:fs");
  const config = JSON.parse(
    readFileSync(
      new URL("../../../src-tauri/tauri.conf.json", import.meta.url),
      "utf8",
    ),
  );
  const policy = config.app.security.csp;
  expect(policy).toContain("'wasm-unsafe-eval'");
  expect(policy).not.toMatch(/(?:^|\s)'unsafe-eval'(?:\s|;|$)/);
});
