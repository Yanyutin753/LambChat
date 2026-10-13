import { fileURLToPath } from "node:url";
import { loadConfigFromFile } from "vite";
import { expect, test } from "vitest";

test("vitest serializes files and concurrent cases with one worker", async () => {
  const loaded = await loadConfigFromFile(
    { command: "serve", mode: "test" },
    fileURLToPath(new URL("../../vitest.config.ts", import.meta.url)),
  );
  expect(loaded?.config).toHaveProperty("test", expect.objectContaining({
    maxWorkers: 1,
    fileParallelism: false,
    maxConcurrency: 1,
  }));
});
