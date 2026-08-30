import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));

test("fork button shows a spinner and disables while forking", () => {
  const source = readFileSync(resolve(currentDir, "../index.tsx"), "utf8");

  // 分叉耗时长，点击后按钮进入 loading 态而不是无反馈
  expect(source).toMatch(/const \[isForking, setIsForking\] = useState\(false\)/);
  expect(source).toMatch(/setIsForking\(true\)/);
  expect(source).toMatch(/finally\s*\{[\s\S]*?setIsForking\(false\)/);
  expect(source).toMatch(/isForking \? \(\s*<Loader2[^>]*animate-spin/);
  expect(source).toMatch(/: \(\s*<GitBranch size=\{16\} \/>/);
  expect(source).toMatch(/disabled=\{isForking\}/);
});

test("fork click awaits the handler instead of fire-and-forget void", () => {
  const source = readFileSync(resolve(currentDir, "../index.tsx"), "utf8");

  expect(source).not.toMatch(/void onForkMessage\(message\.id\)/);
  expect(source).toMatch(/await onForkMessage\(message\.id\)/);
});
