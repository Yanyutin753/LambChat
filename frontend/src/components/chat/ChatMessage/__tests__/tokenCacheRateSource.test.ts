import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const frontendSrc = resolve(currentDir, "../../../..");

function readJson(path: string) {
  return JSON.parse(readFileSync(path, "utf8"));
}

test("token details popover computes cache rate on the frontend", () => {
  const source = readFileSync(resolve(currentDir, "../index.tsx"), "utf8");

  expect(source).toMatch(/const cacheRate =/);
  expect(source).toMatch(/cache_read_tokens/);
  expect(source).toMatch(/input_tokens/);
  expect(source).toMatch(/t\("chat\.message\.tokenCacheRate"\)/);
  // 口径统一：单消息缓存率复用快照的归一化 helper（兼容 provider 两种
  // input_tokens 口径且 clamp ≤100%），不再使用裸除法。
  expect(source).toMatch(/cacheHitRateFromTokens\(/);
  expect(source).not.toMatch(
    /cache_read_tokens \?\? 0\) \/ tokenUsage\.input_tokens/,
  );
});

test("token details popover is viewport anchored so it cannot cover or be clipped by the message", () => {
  const source = readFileSync(resolve(currentDir, "../index.tsx"), "utf8");

  expect(source).toMatch(/const popupStyle = useStickyDropdownPosition\(/);
  expect(source).toMatch(/position: "fixed"/);
  expect(source).toMatch(/createPortal\(/);
  expect(source).not.toMatch(/absolute bottom-full mb-2 left-0 z-50/);
});

test("token details popover clamps inside the viewport instead of being clipped at the top", () => {
  const source = readFileSync(resolve(currentDir, "../index.tsx"), "utf8");
  const start = source.indexOf("function TokenDetailsButton");
  const end = source.indexOf("function GoalDetailsButton");
  const buttonSource = source.slice(start, end);
  expect(start).toBeGreaterThan(-1);
  expect(end).toBeGreaterThan(start);

  // 高度不足时不允许溢出视口：top 钳制在 [8, innerHeight - popupHeight - 8]
  expect(buttonSource).not.toMatch(/translateY\(-100%\)/);
  expect(buttonSource).toMatch(/Math\.max\(\s*8,/);
  expect(buttonSource).toMatch(
    /Math\.min\(desiredTop, window\.innerHeight - popupHeight - 8\)/,
  );
  // 弹层随内容高度变化（费用明细展开/收起）重新定位
  expect(buttonSource).toMatch(/costExpanded/);
});

test("token details popover keeps one accent color per metric row", () => {
  const source = readFileSync(resolve(currentDir, "../index.tsx"), "utf8");
  const start = source.indexOf("function TokenDetailsButton");
  const end = source.indexOf("function GoalDetailsButton");
  const buttonSource = source.slice(start, end);
  expect(start).toBeGreaterThan(-1);
  expect(end).toBeGreaterThan(start);

  // 每行一个专属强调色：输入/输出/缓存写入/缓存率/缓存读取/总计与费用
  expect(buttonSource).toMatch(/text-sky-600 dark:text-sky-400/);
  expect(buttonSource).toMatch(/text-violet-600 dark:text-violet-400/);
  expect(buttonSource).toMatch(/text-emerald-600 dark:text-emerald-400/);
  expect(buttonSource).toMatch(/text-fuchsia-600 dark:text-fuchsia-400/);
  expect(buttonSource).toMatch(/text-pink-600 dark:text-pink-400/);
  expect(buttonSource).toMatch(/text-amber-600 dark:text-amber-400/);
});

test("cache rate label is available in every locale", () => {
  for (const locale of ["en", "zh", "ja", "ko", "ru"]) {
    const messages = readJson(
      resolve(frontendSrc, "i18n", "locales", `${locale}.json`),
    ).chat.message;

    expect(typeof messages.tokenCacheRate).toBe("string");
    expect(messages.tokenCacheRate.trim()).not.toBe("");
  }
});
