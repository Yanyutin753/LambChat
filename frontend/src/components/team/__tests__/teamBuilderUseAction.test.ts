import { readFileSync } from "node:fs";
const wrapperSource = readFileSync(
  new URL("../TeamBuilderWrapper.tsx", import.meta.url),
  "utf8",
);

test("team cards expose a use action that opens chat in team mode", () => {
  expect(wrapperSource).toMatch(/Sparkles/);
  expect(wrapperSource).toMatch(/handleUseTeam/);
  expect(wrapperSource).toMatch(
    /navigate\(`\/chat\?agent=team&team=\$\{encodeURIComponent\(team\.id\)\}`/,
  );
  expect(wrapperSource).toMatch(/title=\{t\("team\.use"/);
});

test("team use action has locale entries", () => {
  const zhLocale = JSON.parse(
    readFileSync(
      new URL("../../../i18n/locales/zh.json", import.meta.url),
      "utf8",
    ),
  );
  expect(zhLocale.team.use).toBe("使用");
  expect(zhLocale.team.useSuccess).toMatch(/^已切换到团队/);
});
