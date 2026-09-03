/** @vitest-environment jsdom */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, vi } from "vitest";
import { ComposerUsageChip } from "../ComposerUsageChip";
import type { UsageStats } from "../../../types/usage";

const { getStatsMock, navigateMock } = vi.hoisted(() => ({
  getStatsMock: vi.fn(),
  navigateMock: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { amount?: string }) => {
      const map: Record<string, string> = {
        "usage.todaySpend": "今日用量",
        "usage.tokenMix": "Token 构成",
        "usage.tokensInput": "输入",
        "usage.tokensOutput": "输出",
        "usage.cacheWrite": "缓存写入",
        "usage.cacheRead": "缓存读取",
        "usage.requestsCount": "请求数",
        "usage.cacheHitRate": "缓存命中",
        "usage.viewDetails": "查看详情",
      };
      if (key === "usage.todayShort") return `今日 ${opts?.amount}`;
      return map[key] ?? key;
    },
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

vi.mock("react-router-dom", () => ({
  useNavigate: () => navigateMock,
}));

function todayStats(overrides: Partial<UsageStats> = {}): UsageStats {
  return {
    total_requests: 3,
    total_input_tokens: 100,
    total_output_tokens: 50,
    total_tokens: 150,
    total_cache_creation_tokens: 20,
    total_cache_read_tokens: 30,
    total_cost_usd: 0.5,
    total_duration: 12,
    ...overrides,
  };
}

beforeEach(() => {
  getStatsMock.mockReset();
  navigateMock.mockReset();
});

test("renders nothing while stats are unavailable", async () => {
  getStatsMock.mockReturnValue(new Promise(() => {}));
  const { container } = render(<ComposerUsageChip />);
  await act(async () => {});
  expect(container).toBeEmptyDOMElement();
});

test("shows the amount and opens the usage card on click", async () => {
  getStatsMock.mockResolvedValue(todayStats());
  render(<ComposerUsageChip />);

  const trigger = await screen.findByRole("button", { name: /今日 ¥3\.60/ });
  fireEvent.click(trigger);

  expect(await screen.findByText("今日用量")).toBeInTheDocument();
  expect(screen.getByText("Token 构成")).toBeInTheDocument();
  expect(screen.getByText("请求数")).toBeInTheDocument();
  expect(screen.getByText("3")).toBeInTheDocument();
  // 缓存命中率 = 30 / 100 = 30.0%（input 已包含缓存读取 token）
  expect(screen.getByText("30.0%")).toBeInTheDocument();
  // 四类 token 明细
  expect(screen.getByText("输入")).toBeInTheDocument();
  expect(screen.getByText("输出")).toBeInTheDocument();
  expect(screen.getByText("缓存写入")).toBeInTheDocument();
  expect(screen.getByText("缓存读取")).toBeInTheDocument();

  fireEvent.click(screen.getByText("查看详情"));
  expect(navigateMock).toHaveBeenCalledWith("/usage");
});

test("refreshes when a chat round settles via the window event", async () => {
  getStatsMock.mockResolvedValue(todayStats());
  render(<ComposerUsageChip />);
  await screen.findByRole("button", { name: /今日 ¥3\.60/ });
  expect(getStatsMock).toHaveBeenCalledTimes(1);

  await act(async () => {
    window.dispatchEvent(new Event("today-usage-refresh"));
  });
  expect(getStatsMock).toHaveBeenCalledTimes(2);
});

test("queues a follow-up refresh when the event lands while a fetch is in flight", async () => {
  let resolveFirst!: (stats: UsageStats) => void;
  getStatsMock.mockImplementationOnce(
    () => new Promise<UsageStats>((resolve) => (resolveFirst = resolve)),
  );
  getStatsMock.mockResolvedValue(todayStats());
  render(<ComposerUsageChip />);

  // 首次拉取仍在途时收到刷新事件（如 WS 推送撞上 SSE 关流刷新）：不得并发，也不得丢弃
  act(() => {
    window.dispatchEvent(new Event("today-usage-refresh"));
  });
  expect(getStatsMock).toHaveBeenCalledTimes(1);

  await act(async () => {
    resolveFirst(todayStats());
  });
  expect(getStatsMock).toHaveBeenCalledTimes(2);
});

test("chat input notifies the usage chip when a run settles", () => {
  const chatDir = dirname(fileURLToPath(import.meta.url));
  const source = readFileSync(resolve(chatDir, "../ChatInput.tsx"), "utf8");
  expect(source).toMatch(/useNotifyTodayUsageRefresh\(isLoading\)/);
});

test("usage chip matches the toolbar chip look: borderless, blue serif label, 16px", () => {
  const chatDir = dirname(fileURLToPath(import.meta.url));
  const source = readFileSync(
    resolve(chatDir, "../ComposerUsageChip.tsx"),
    "utf8",
  );
  expect(source).not.toMatch(/1px solid var\(--theme-border\)/);
  expect(source).toMatch(/chat-tool-btn/);
  expect(source).toMatch(/text-blue-600 dark:text-blue-400 font-serif/);
  expect(source).toMatch(/<Activity size=\{16\}/);

  const toolbarSource = readFileSync(
    resolve(chatDir, "../ChatInputToolbar.tsx"),
    "utf8",
  );
  expect(toolbarSource).not.toMatch(
    /border: "1px solid var\(--theme-border\)"/,
  );
});

test("toolbar renders the usage chip in the right-side action group", () => {
  const chatDir = dirname(fileURLToPath(import.meta.url));
  const source = readFileSync(
    resolve(chatDir, "../ChatInputToolbar.tsx"),
    "utf8",
  );
  expect(source).toMatch(/<ComposerUsageChip \/>/);
  // 位于设置按钮之前、右侧动作组之内
  expect(source.indexOf("<ComposerUsageChip />")).toBeLessThan(
    source.indexOf("data-run-mode-trigger"),
  );
});

test("view details footer spreads label left and chevron right", () => {
  const chatDir = dirname(fileURLToPath(import.meta.url));
  const source = readFileSync(
    resolve(chatDir, "../ComposerUsageChip.tsx"),
    "utf8",
  );
  const footer = source.slice(source.indexOf("详情入口"));
  expect(footer).toMatch(/items-center justify-between/);
  expect(footer).not.toMatch(/justify-center/);
});

test("usage card labels are defined in every locale", () => {
  const localeDir = resolve(
    dirname(fileURLToPath(import.meta.url)),
    "../../../i18n/locales",
  );
  for (const locale of ["en", "zh", "ja", "ko", "ru"]) {
    const messages = JSON.parse(
      readFileSync(resolve(localeDir, `${locale}.json`), "utf8"),
    );
    for (const key of [
      "todaySpend",
      "tokenMix",
      "tokensInput",
      "tokensOutput",
      "requestsCount",
      "viewDetails",
    ]) {
      expect(typeof messages.usage[key]).toBe("string");
      expect(messages.usage[key].trim()).not.toBe("");
    }
    expect(messages.usage.todayShort).toContain("{{amount}}");
  }
});
