/** @vitest-environment jsdom */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { render, screen } from "@testing-library/react";
import { beforeEach, vi } from "vitest";
import { ComposerFootnote } from "../ComposerFootnote";
import type { UsageStats } from "../../../types/usage";

const { getStatsMock } = vi.hoisted(() => ({ getStatsMock: vi.fn() }));

const DISCLAIMER = "AI 生成内容可能出错，请注意核实";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { amount?: string }) =>
      key === "usage.todayCost"
        ? `今日已用 ${opts?.amount}`
        : key === "chat.aiDisclaimer"
          ? DISCLAIMER
          : key,
    i18n: { language: "zh" },
  }),
}));

vi.mock("../../../hooks/useFxRates", () => ({
  useFxRates: () => ({ base: "USD", rates: { CNY: 7.2 }, synced_at: null }),
}));

vi.mock("../../../services/api/usage", () => ({
  usageApi: {
    getStats: (...args: unknown[]) => getStatsMock(...args),
  },
}));

function todayStats(overrides: Partial<UsageStats> = {}): UsageStats {
  return {
    total_requests: 3,
    total_input_tokens: 100,
    total_output_tokens: 50,
    total_tokens: 150,
    total_cache_creation_tokens: 0,
    total_cache_read_tokens: 0,
    total_cost_usd: 0.5,
    total_duration: 12,
    ...overrides,
  };
}

beforeEach(() => {
  getStatsMock.mockReset();
});

test("shows the AI disclaimer even before stats load", () => {
  getStatsMock.mockReturnValue(new Promise(() => {}));
  render(<ComposerFootnote />);
  expect(screen.getByText(DISCLAIMER)).toBeInTheDocument();
  expect(screen.queryByText(/今日已用/)).not.toBeInTheDocument();
});

test("appends today's spend in the display currency once stats load", async () => {
  getStatsMock.mockResolvedValue(todayStats());
  render(<ComposerFootnote />);
  expect(await screen.findByText("今日已用 ¥3.60")).toBeInTheDocument();
  expect(screen.getByText(DISCLAIMER)).toBeInTheDocument();
  // 今日按客户端本地 0 点计算，而不是后端 UTC 0 点或滚动 24 小时
  expect(getStatsMock).toHaveBeenCalledWith({
    period: "today",
    start_date: expect.any(String),
  });
});

test("keeps the disclaimer without spend when stats fail to load", () => {
  getStatsMock.mockRejectedValue(new Error("network"));
  const { container } = render(<ComposerFootnote />);
  expect(container.textContent).toBe(DISCLAIMER);
});

test("refreshes after a run settles", async () => {
  getStatsMock.mockResolvedValue(todayStats());
  const view = render(<ComposerFootnote isLoading />);
  await screen.findByText("今日已用 ¥3.60");
  expect(getStatsMock).toHaveBeenCalledTimes(1);

  view.rerender(<ComposerFootnote isLoading={false} />);
  await screen.findByText("今日已用 ¥3.60");
  expect(getStatsMock).toHaveBeenCalledTimes(2);
});

test("chat input renders the footnote below the composer form", () => {
  const chatDir = dirname(fileURLToPath(import.meta.url));
  const source = readFileSync(resolve(chatDir, "../ChatInput.tsx"), "utf8");
  const toolbarSource = readFileSync(
    resolve(chatDir, "../ChatInputToolbar.tsx"),
    "utf8",
  );

  expect(source).toMatch(/<ComposerFootnote isLoading=\{isLoading\} \/>/);
  // 渲染位置在 </form> 之后（输入框下方）
  expect(source.indexOf("</form>")).toBeLessThan(
    source.indexOf("<ComposerFootnote"),
  );
  expect(toolbarSource).not.toMatch(/ComposerFootnote|DailyUsage/);
});

test("footnote labels are defined in every locale", () => {
  const localeDir = resolve(
    dirname(fileURLToPath(import.meta.url)),
    "../../../i18n/locales",
  );
  for (const locale of ["en", "zh", "ja", "ko", "ru"]) {
    const messages = JSON.parse(
      readFileSync(resolve(localeDir, `${locale}.json`), "utf8"),
    );
    expect(typeof messages.chat.aiDisclaimer).toBe("string");
    expect(messages.chat.aiDisclaimer.trim()).not.toBe("");
    expect(messages.usage.todayCost).toContain("{{amount}}");
  }
});
