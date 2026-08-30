/** @vitest-environment jsdom */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { SidebarUserRow } from "../SidebarUserRow";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => (key === "common.user" ? "用户" : key),
    i18n: { language: "zh" },
  }),
}));

// 桶文件在模块顶层初始化 i18n，与上面的 react-i18next mock 冲突，stub 掉即可
vi.mock("../../../../services/api", () => ({
  getFullUrl: (url: string) => url,
}));

const user = {
  username: "clivia.yang",
  avatar_url: undefined,
  roles: ["admin"],
};

test("renders the username, capitalized role and affordance icon", () => {
  render(
    <SidebarUserRow user={user} imgError={false} onShowProfile={() => {}} />,
  );
  expect(screen.getByText("clivia.yang")).toBeInTheDocument();
  expect(screen.getByText("Admin")).toBeInTheDocument();
});

test("sidebar footer delegates the user row to SidebarUserRow", () => {
  const testDir = dirname(fileURLToPath(import.meta.url));
  const source = readFileSync(
    resolve(testDir, "../SessionListContent.tsx"),
    "utf8",
  );
  expect(source).toMatch(/<SidebarUserRow/);
  // 用量展示收在输入框 ComposerUsageChip，不进侧边栏用户行
  expect(source).not.toMatch(/useTodayUsageCost/);
});
