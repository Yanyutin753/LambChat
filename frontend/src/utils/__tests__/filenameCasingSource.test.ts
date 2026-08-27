import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { test, expect } from "vitest";

// 同目录下 basename 仅差大小写的 .ts/.tsx 文件对客户端构建是地雷：
// 大小写不敏感文件系统（macOS/Windows）上 TS 的无扩展名导入会解析到错误文件
// （v2.7.0 的 RunStepsCollapse.tsx ↔ runStepsCollapse.ts 曾炸掉全部客户端构建）。
// 新增文件若与本测试冲突，请重命名（如加 Utils 后缀）而不是加白名单。

const SRC_ROOT = new URL("../..", import.meta.url).pathname;

function listFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    if (name === "__tests__" || name === "node_modules" || name.startsWith("."))
      continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      out.push(...listFiles(p));
    } else if (/\.(ts|tsx)$/.test(name)) {
      out.push(p);
    }
  }
  return out;
}

test("no same-directory ts/tsx basenames collide case-insensitively", () => {
  const byDir = new Map<string, string[]>();
  for (const file of listFiles(SRC_ROOT)) {
    const parts = file.split("/");
    const name = parts.pop() as string;
    const dir = parts.join("/");
    const list = byDir.get(dir) ?? [];
    list.push(name);
    byDir.set(dir, list);
  }

  const offenders: string[] = [];
  for (const [dir, names] of byDir) {
    const seen = new Map<string, string>();
    for (const name of names) {
      const stem = name.replace(/\.(ts|tsx)$/, "").toLowerCase();
      const exact = name.replace(/\.(ts|tsx)$/, "");
      const prev = seen.get(stem);
      if (prev !== undefined && prev !== exact) {
        offenders.push(`${dir}: ${prev} ↔ ${exact}`);
      }
      seen.set(stem, exact);
    }
  }

  expect(offenders).toEqual([]);
});
