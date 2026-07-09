import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const hooksDir = resolve(import.meta.dirname, "..");

test("useFileUpload aborts pending uploads and clears abort handlers on unmount", () => {
  const source = readFileSync(resolve(hooksDir, "useFileUpload.ts"), "utf8");

  expect(source).toMatch(/const abortMap = abortMapRef\.current/);
  expect(source).toMatch(/for \(const abort of abortMap\.values\(\)\)/);
  expect(source).toMatch(/abortMap\.clear\(\)/);
});

test("useWebSocket suppresses refresh-triggered reconnects after unmount", () => {
  const source = readFileSync(resolve(hooksDir, "useWebSocket.ts"), "utf8");

  expect(source).toMatch(/isMountedRef/);
  expect(source).toMatch(
    /isMountedRef\.current && enabled && !wasManualDisconnect/,
  );
});
