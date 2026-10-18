/** @vitest-environment jsdom */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, vi } from "vitest";
import { ComposerUsageChip } from "../ComposerUsageChip";
import type { UsageStats } from "../../../types/usage";

const { getStatsMock, getQuotaMock, consumeCardMock, navigateMock } =
  vi.hoisted(() => ({
    getStatsMock: vi.fn(),
    getQuotaMock: vi.fn(),
    consumeCardMock: vi.fn(),
    navigateMock: vi.fn(),
  }));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { amount?: string; count?: number }) => {
      const map: Record<string, string> = {
        "usage.todaySpend": "今日用量",
        "usage.tokenMix": "Token 构成",
        "usage.tokensInput": "输入",
        "usage.tokensInputReported": "输入（报告值）",
        "usage.tokensOutput": "输出",
        "usage.cacheWrite": "缓存写入",
        "usage.cacheRead": "缓存读取",
        "usage.requestsCount": "请求数",
        "usage.cacheHitRate": "缓存命中",
        "usage.viewDetails": "查看详情",
      };
      if (key === "usage.todayShort") return `今日 ${opts?.amount}`;
      if (key === "usage.resetCardsShort") return `重置卡 ${opts?.count}`;
      return map[key] ?? key;
    },
    i18n: { language: "zh" },
  }),
}));

vi.mock("../../../hooks/useFxRates", () => ({
  useFxRates: () => ({ base: "USD", rates: { CNY: 7.2 }, synced_at: null }),
}));

vi.mock("../../../services/api/fetch", () => ({ authFetch: vi.fn() }));
vi.mock("../../../services/api/usage", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../services/api/usage")>()),
  usageApi: {
    getStats: (...args: unknown[]) => getStatsMock(...args),
    getQuota: (...args: unknown[]) => getQuotaMock(...args),
    consumeResetCard: (...args: unknown[]) => consumeCardMock(...args),
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
    cache_unknown_requests: 0,
    ...overrides,
  };
}

beforeEach(() => {
  getStatsMock.mockReset();
  getQuotaMock.mockReset().mockReturnValue(new Promise(() => {}));
  navigateMock.mockReset();
  consumeCardMock.mockReset();
});

function confirmReset() {
  fireEvent.click(
    within(screen.getByRole("dialog")).getByRole("button", {
      name: "common.reset",
    }),
  );
}

test("keeps quota loading accessible while token stats are unavailable", async () => {
  getStatsMock.mockReturnValue(new Promise(() => {}));
  render(<ComposerUsageChip />);
  fireEvent.click(await screen.findByRole("button", { name: "今日 —" }));
  expect(await screen.findByText("usage.quotaLoading")).toBeInTheDocument();
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

test("unknown cost stays unknown while available token counts still produce percentages", async () => {
  getStatsMock.mockResolvedValue(
    todayStats({
      total_cost_usd: 0,
      priced_requests: 0,
      unpriced_requests: 3,
      cache_unknown_requests: 1,
      usage_unknown_requests: 1,
    }),
  );
  render(<ComposerUsageChip />);
  fireEvent.click(await screen.findByRole("button", { name: "今日 —" }));
  expect(await screen.findByText("Token 构成")).toBeInTheDocument();
  expect(screen.getByText("30.0%")).toBeInTheDocument();
  expect(screen.getByText("输入")).toBeInTheDocument();
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

test("usage chip uses a borderless neutral serif label and 16px icon", () => {
  const chatDir = dirname(fileURLToPath(import.meta.url));
  const source = readFileSync(
    resolve(chatDir, "../ComposerUsageChip.tsx"),
    "utf8",
  );
  expect(source).not.toMatch(/1px solid var\(--theme-border\)/);
  expect(source).toMatch(/chat-tool-btn/);
  expect(source).toMatch(/text-theme-text-secondary font-serif/);
  expect(source).not.toMatch(/text-blue-/);
  expect(source).not.toContain('t("usage.partialCostHint")');
  expect(source).toMatch(/<Activity size=\{16\}/);

  const toolbarSource = readFileSync(
    resolve(chatDir, "../ChatInputToolbar.tsx"),
    "utf8",
  );
  expect(toolbarSource).not.toMatch(
    /border: "1px solid var\(--theme-border\)"/,
  );
});

test("header renders today's usage next to the user menu, outside the composer", () => {
  const chatDir = dirname(fileURLToPath(import.meta.url));
  const header = readFileSync(
    resolve(chatDir, "../../layout/AppContent/Header.tsx"),
    "utf8",
  );
  const toolbar = readFileSync(
    resolve(chatDir, "../ChatInputToolbar.tsx"),
    "utf8",
  );
  expect(toolbar).not.toContain("ComposerUsageChip");
  const actions = header.slice(header.indexOf("chat-header__actions"));
  expect(actions).toContain("<ComposerUsageChip ");
  expect(actions.indexOf("<ComposerUsageChip ")).toBeLessThan(
    actions.indexOf("<UserMenu"),
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

test("usage card uses serif text and aligns metric columns and baselines", async () => {
  getStatsMock.mockResolvedValue(todayStats());
  render(<ComposerUsageChip />);
  fireEvent.click(await screen.findByRole("button", { name: /今日 ¥3\.60/ }));
  expect(document.getElementById("composer-usage-popover")).toHaveClass(
    "font-serif",
  );
  expect(screen.getByText("输入").parentElement).toHaveClass("grid");
  expect(screen.getByText("输入").parentElement).toHaveClass("items-baseline");
  const popover = document.getElementById("composer-usage-popover")!;
  expect(popover).toHaveStyle({ paddingInline: "1.125rem" });
  expect(popover.querySelectorAll(".px-3")).toHaveLength(0);
  expect(screen.getByText("输入").parentElement!.children[2]).toHaveClass(
    "text-right",
    "tabular-nums",
  );
  expect(screen.getByText("3").parentElement).toHaveClass(
    "inline-flex",
    "items-baseline",
  );
});

test("56 requests calculate available token counts despite missing provider metrics", async () => {
  getStatsMock.mockResolvedValue(
    todayStats({
      total_requests: 56,
      total_cache_creation_tokens: 0,
      cache_unknown_requests: 56,
      usage_unknown_requests: 56,
      unknown_usage_fields: ["cache_creation_tokens"],
    }),
  );
  render(<ComposerUsageChip />);
  fireEvent.click(await screen.findByRole("button", { name: /今日 ¥3\.60/ }));
  const input = await screen.findByText("输入");
  expect(within(input.parentElement!).getByText("70")).toBeInTheDocument();
  expect(
    within(screen.getByText("输出").parentElement!).getByText("50"),
  ).toBeInTheDocument();
  expect(
    within(screen.getByText("缓存读取").parentElement!).getByText("30"),
  ).toBeInTheDocument();
  expect(
    within(screen.getByText("缓存写入").parentElement!).getByText("0"),
  ).toBeInTheDocument();
  expect(screen.getByText("30.0%")).toBeInTheDocument();
  expect(screen.getByText("56")).toBeInTheDocument();
});

test("mixed observations display available totals without plus signs or unknown warnings", async () => {
  getStatsMock.mockResolvedValue(
    todayStats({
      total_requests: 60,
      total_cache_creation_tokens: 0,
      usage_unknown_requests: 60,
      cache_unknown_requests: 2,
      unknown_usage_fields: [
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
      ],
    }),
  );
  render(<ComposerUsageChip />);
  fireEvent.click(await screen.findByRole("button", { name: /今日 ¥3\.60/ }));
  expect(screen.getByText("70")).toBeInTheDocument();
  expect(screen.getByText("50")).toBeInTheDocument();
  expect(screen.getByText("30")).toBeInTheDocument();
  expect(screen.queryByText("usage.partialTokensHint")).toBeNull();
  expect(screen.queryByText("usage.cacheRateUnknown")).toBeNull();
  expect(screen.queryByText("100+")).toBeNull();
  const write = within(screen.getByText("缓存写入").parentElement!);
  expect(write.getByText("0")).toBeInTheDocument();
  expect(screen.getByText("30.0%")).toBeInTheDocument();
});

test("quota bars use distinct theme colors in both browser engines", () => {
  const chatDir = dirname(fileURLToPath(import.meta.url));
  const css = readFileSync(
    resolve(chatDir, "../../../styles/chat.css"),
    "utf8",
  );
  expect(css).toMatch(
    /\[data-period="five_hour"\][\s\S]*?--quota-progress-color: var\(--color-icon-blue\)/,
  );
  expect(css).toMatch(
    /\[data-period="weekly"\][\s\S]*?--quota-progress-color: var\(--color-icon-purple\)/,
  );
  for (const selector of ["::-webkit-progress-value", "::-moz-progress-bar"]) {
    expect(
      css.slice(css.indexOf(`.usage-quota-progress${selector}`)).split("}")[0],
    ).toContain("var(--quota-progress-color)");
  }
});

function quotaWindow(overrides = {}) {
  return {
    limit_usd: 10,
    used_usd: 2,
    reserved_usd: 1,
    remaining_usd: 7,
    reset_at: "2026-10-19T00:00:00+08:00",
    blocked: false,
    unknown: false,
    ...overrides,
  };
}

test("shows two compact colored quota columns with percentages and reset times", async () => {
  getStatsMock.mockRejectedValue(new Error("No stats"));
  getQuotaMock.mockResolvedValue({
    currency: "USD",
    timezone: "Asia/Shanghai",
    five_hour: quotaWindow(),
    weekly: quotaWindow({ limit_usd: 20, remaining_usd: 17 }),
  });
  render(<ComposerUsageChip />);
  fireEvent.click(await screen.findByRole("button", { name: "今日 —" }));
  expect(await screen.findByText("usage.quotaFiveHour")).toBeInTheDocument();
  const section = screen.getByRole("region", { name: "usage.quotaTitle" });
  expect(
    within(section)
      .getAllByRole("progressbar")
      .map((bar) => bar.getAttribute("value")),
  ).toEqual(["70", "85"]);
  expect(
    within(section).getByText("70%").closest("[data-period]")?.parentElement,
  ).toHaveClass("grid", "grid-cols-2");
  expect(within(section).getByText("00:00")).toBeInTheDocument();
  expect(within(section).getByText("10月19日")).toBeInTheDocument();
  expect(section).not.toHaveTextContent("$");
  expect(section).not.toHaveTextContent("Asia/Shanghai");
  expect(section).not.toHaveTextContent("usage.quotaReserved");
  expect(screen.getByText("70%")).toBeInTheDocument();
  expect(screen.getByText("85%")).toBeInTheDocument();
  expect(screen.queryByText("Token 构成")).toBeNull();
  expect(document.querySelectorAll("time[datetime]")).toHaveLength(2);
  await act(async () => {
    window.dispatchEvent(new Event("today-usage-refresh"));
  });
  expect(getQuotaMock).toHaveBeenCalledTimes(3);
  expect(getQuotaMock).toHaveBeenCalledWith(expect.any(AbortSignal));
});

test.each([
  [9.975, "99.8%"],
  [9.9999, "<100%"],
  [0.0001, ">0%"],
  [10, "100%"],
])(
  "remaining quota %s does not round away actual usage",
  async (remaining, label) => {
    getStatsMock.mockRejectedValue(new Error("No stats"));
    getQuotaMock.mockResolvedValue({
      currency: "USD",
      timezone: "Asia/Shanghai",
      five_hour: quotaWindow({
        used_usd: 10 - remaining,
        remaining_usd: remaining,
      }),
      weekly: quotaWindow(),
    });
    render(<ComposerUsageChip />);
    fireEvent.click(await screen.findByRole("button", { name: "今日 —" }));
    const section = screen.getByRole("region", { name: "usage.quotaTitle" });
    expect(await within(section).findByText(label)).toBeInTheDocument();
    if (remaining < 10) expect(within(section).queryByText("100%")).toBeNull();
  },
);

test("quota failures show an explicit unavailable state", async () => {
  getStatsMock.mockResolvedValue(todayStats());
  getQuotaMock.mockRejectedValue(new Error("Offline"));
  render(<ComposerUsageChip />);
  fireEvent.click(await screen.findByRole("button", { name: /今日 ¥3\.60/ }));
  expect(await screen.findByText("usage.quotaUnavailable")).toBeInTheDocument();
});

test("unknown costs preserve settled quota availability and zero limits stay blocked", async () => {
  getStatsMock.mockResolvedValue(todayStats());
  getQuotaMock.mockResolvedValue({
    currency: "USD",
    timezone: "Asia/Shanghai",
    five_hour: quotaWindow({ unknown: true }),
    weekly: quotaWindow({ limit_usd: 0, remaining_usd: 0, blocked: true }),
  });
  render(<ComposerUsageChip />);
  fireEvent.click(await screen.findByRole("button", { name: /今日 ¥3\.60/ }));
  const quotaBar = await screen.findByRole("progressbar", {
    name: "usage.quotaFiveHour",
  });
  expect(screen.queryByText("usage.quotaUnknown")).toBeNull();
  expect(quotaBar).not.toHaveAttribute("title", "usage.quotaUnknown");
  expect(quotaBar).not.toHaveAttribute("aria-valuetext", "usage.quotaUnknown");
  expect(screen.getByText("usage.quotaBlocked")).toBeInTheDocument();
  expect(screen.getByText("0%")).toBeInTheDocument();
  expect(
    screen.getByRole("progressbar", { name: "usage.quotaFiveHour" }),
  ).toHaveAttribute("value", "70");
  expect(screen.getByText("70%")).toBeInTheDocument();
  expect(document.querySelectorAll("time[datetime]")).toHaveLength(2);
});

test("unlimited quotas show full availability and reset times while preserving queued refreshes", async () => {
  let resolveFirst!: (quota: unknown) => void;
  const unlimited = {
    currency: "USD",
    timezone: "Asia/Shanghai",
    five_hour: quotaWindow({ limit_usd: null, remaining_usd: null }),
    weekly: quotaWindow({ limit_usd: null, remaining_usd: null }),
  };
  getStatsMock.mockResolvedValue(todayStats());
  getQuotaMock.mockImplementationOnce(
    () => new Promise((resolve) => (resolveFirst = resolve)),
  );
  getQuotaMock.mockResolvedValue(unlimited);
  render(<ComposerUsageChip />);
  act(() => window.dispatchEvent(new Event("today-usage-refresh")));
  expect(getQuotaMock).toHaveBeenCalledTimes(1);
  await act(async () => resolveFirst(unlimited));
  expect(getQuotaMock).toHaveBeenCalledTimes(2);
  fireEvent.click(await screen.findByRole("button", { name: /今日 ¥3\.60/ }));
  const bars = await screen.findAllByRole("progressbar");
  expect(bars).toHaveLength(2);
  for (const bar of bars) {
    expect(bar).toHaveAttribute("value", "100");
    expect(bar).toHaveAttribute("aria-valuetext", "usage.quotaUnlimited");
  }
  expect(screen.queryByText("usage.quotaUnlimited")).toBeNull();
  expect(screen.getAllByText("100%")).toHaveLength(2);
  expect(document.querySelectorAll("time[datetime]")).toHaveLength(2);
  expect(screen.getByText("00:00")).toBeInTheDocument();
  expect(screen.getByText("10月19日")).toBeInTheDocument();
});

test("opening the popover refreshes quota without refetching token statistics", async () => {
  const quota = {
    currency: "USD",
    timezone: "Asia/Shanghai",
    five_hour: quotaWindow(),
    weekly: quotaWindow(),
  };
  getStatsMock.mockResolvedValue(todayStats());
  getQuotaMock.mockResolvedValueOnce(quota).mockResolvedValue({
    ...quota,
    five_hour: quotaWindow({ remaining_usd: 4, reserved_usd: 4 }),
  });
  render(<ComposerUsageChip />);
  await act(async () => {});
  expect(getQuotaMock).toHaveBeenCalledTimes(1);
  fireEvent.click(await screen.findByRole("button", { name: /今日 ¥3\.60/ }));
  expect(await screen.findByText("40%")).toBeInTheDocument();
  expect(getQuotaMock).toHaveBeenCalledTimes(2);
  expect(getStatsMock).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: /今日 ¥3\.60/ }));
  expect(getQuotaMock).toHaveBeenCalledTimes(2);
});

test("unused quota windows show their balance without timer details", async () => {
  getStatsMock.mockResolvedValue(todayStats());
  getQuotaMock.mockResolvedValue({
    currency: "USD",
    timezone: "Asia/Shanghai",
    five_hour: quotaWindow({ reset_at: null }),
    weekly: quotaWindow({ reset_at: null }),
  });
  render(<ComposerUsageChip />);
  fireEvent.click(await screen.findByRole("button", { name: /今日 ¥3\.60/ }));
  expect(await screen.findAllByText("70%")).toHaveLength(2);
  expect(screen.queryByText("usage.quotaWindowNotStarted")).toBeNull();
  expect(document.querySelectorAll("time[datetime]")).toHaveLength(0);
});

test("unknown costs do not hide exhaustion of the settled budget", async () => {
  getStatsMock.mockResolvedValue(todayStats());
  getQuotaMock.mockResolvedValue({
    currency: "USD",
    timezone: "Asia/Shanghai",
    five_hour: quotaWindow({
      unknown: true,
      blocked: true,
      used_usd: 10,
      remaining_usd: 0,
    }),
    weekly: quotaWindow(),
  });
  render(<ComposerUsageChip />);
  fireEvent.click(await screen.findByRole("button", { name: /今日 ¥3\.60/ }));
  const quotaBar = await screen.findByRole("progressbar", {
    name: "usage.quotaFiveHour",
  });
  expect(screen.queryByText("usage.quotaUnknown")).toBeNull();
  expect(quotaBar).not.toHaveAttribute("title", "usage.quotaUnknown");
  expect(quotaBar).not.toHaveAttribute("aria-valuetext", "usage.quotaUnknown");
  expect(screen.getByText("usage.quotaBlocked")).toBeInTheDocument();
  expect(
    screen.getByRole("progressbar", { name: "usage.quotaFiveHour" }),
  ).toHaveAttribute("value", "0");
});

test("unknown costs preserve unlimited quota availability", async () => {
  getStatsMock.mockResolvedValue(todayStats());
  getQuotaMock.mockResolvedValue({
    currency: "USD",
    timezone: "Asia/Shanghai",
    five_hour: quotaWindow({
      unknown: true,
      limit_usd: null,
      remaining_usd: null,
    }),
    weekly: quotaWindow(),
  });
  render(<ComposerUsageChip />);
  fireEvent.click(await screen.findByRole("button", { name: /今日 ¥3\.60/ }));
  const quotaBar = await screen.findByRole("progressbar", {
    name: "usage.quotaFiveHour",
  });
  expect(screen.queryByText("usage.quotaUnknown")).toBeNull();
  expect(quotaBar).not.toHaveAttribute("title", "usage.quotaUnknown");
  expect(quotaBar).not.toHaveAttribute("aria-valuetext", "usage.quotaUnknown");
  expect(
    screen.getByRole("progressbar", { name: "usage.quotaFiveHour" }),
  ).toHaveAttribute("value", "100");
  expect(screen.getByText("100%")).toBeInTheDocument();
});

test("redeeming a reset card refreshes its balance and reports a no-op without claiming success", async () => {
  const quota = {
    currency: "USD",
    timezone: "Asia/Shanghai",
    five_hour: quotaWindow({
      used_usd: 10,
      reserved_usd: 0,
      remaining_usd: 0,
      blocked: true,
    }),
    weekly: quotaWindow(),
    reset_credits: {
      available_count: 1,
      credits: [
        {
          id: "card-one",
          status: "available",
          granted_at: "2026-10-18T00:00:00Z",
          expires_at: "2026-11-17T00:00:00Z",
        },
      ],
    },
  };
  getStatsMock.mockResolvedValue(todayStats());
  getQuotaMock.mockResolvedValue(quota);
  consumeCardMock.mockResolvedValue({ outcome: "nothingToReset" });
  render(<ComposerUsageChip />);
  fireEvent.click(await screen.findByRole("button", { name: /今日 ¥3\.60/ }));
  const button = await screen.findByRole("button", {
    name: /^usage\.useResetCard \d+$/,
  });
  const callsBefore = getQuotaMock.mock.calls.length;
  fireEvent.click(button);
  confirmReset();
  expect(
    await screen.findByText("usage.resetNothingToReset"),
  ).toBeInTheDocument();
  expect(consumeCardMock).toHaveBeenCalledWith(expect.any(String), "card-one");
  expect(getQuotaMock.mock.calls.length).toBeGreaterThan(callsBefore);
  expect(screen.queryByText("usage.resetSuccess")).toBeNull();
});

test("reset card retries retain the operation key when a response is lost", async () => {
  getStatsMock.mockResolvedValue(todayStats());
  getQuotaMock.mockResolvedValue({
    currency: "USD",
    timezone: "Asia/Shanghai",
    five_hour: quotaWindow({
      used_usd: 10,
      reserved_usd: 0,
      remaining_usd: 0,
      blocked: true,
    }),
    weekly: quotaWindow(),
    reset_credits: {
      available_count: 1,
      credits: [
        {
          id: "card-one",
          status: "available",
          granted_at: "2026-10-18T00:00:00Z",
          expires_at: "2026-11-17T00:00:00Z",
        },
      ],
    },
  });
  consumeCardMock
    .mockRejectedValueOnce(new Error("Lost response"))
    .mockResolvedValue({ outcome: "alreadyRedeemed" });
  render(<ComposerUsageChip />);
  fireEvent.click(await screen.findByRole("button", { name: /今日 ¥3\.60/ }));
  const button = await screen.findByRole("button", {
    name: /^usage\.useResetCard \d+$/,
  });
  fireEvent.click(button);
  confirmReset();
  await screen.findByText("Lost response");
  fireEvent.click(
    screen.getByRole("button", { name: /^usage\.useResetCard \d+$/ }),
  );
  confirmReset();
  expect(
    await screen.findByText("usage.resetAlreadyRedeemed"),
  ).toBeInTheDocument();
  expect(consumeCardMock.mock.calls[0][0]).toEqual(
    consumeCardMock.mock.calls[1][0],
  );
});

test("a hung quota request times out, allows retry, and cannot overwrite newer balances", async () => {
  vi.useFakeTimers();
  let resolveOld!: (value: unknown) => void;
  getStatsMock.mockResolvedValue(todayStats());
  getQuotaMock.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveOld = resolve;
      }),
  );
  const hook = render(<ComposerUsageChip />);
  try {
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name: /今日 ¥3\.60/ }));
    act(() => window.dispatchEvent(new Event("today-usage-refresh")));
    expect(getQuotaMock).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(screen.getByText("usage.quotaUnavailable")).toBeInTheDocument();
    expect(getQuotaMock).toHaveBeenCalledTimes(1);
    expect(getQuotaMock.mock.calls[0][0].aborted).toBe(true);
    const retry = screen.getByRole("button", { name: "common.retry" });
    expect(retry).toBeEnabled();
    const fresh = {
      currency: "USD",
      timezone: "Asia/Shanghai",
      five_hour: quotaWindow({ remaining_usd: 4 }),
      weekly: quotaWindow(),
    };
    getQuotaMock.mockResolvedValue(fresh);
    await act(async () => {
      fireEvent.click(retry);
    });
    expect(screen.getByText("40%")).toBeInTheDocument();
    await act(async () => {
      resolveOld({ ...fresh, five_hour: quotaWindow({ remaining_usd: 1 }) });
    });
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.queryByText("10%")).toBeNull();
  } finally {
    hook.unmount();
    vi.useRealTimers();
  }
});

test("unmount aborts an outstanding quota request", async () => {
  getStatsMock.mockResolvedValue(todayStats());
  const hook = render(<ComposerUsageChip />);
  await act(async () => {});
  const signal = getQuotaMock.mock.calls[0][0] as AbortSignal;
  hook.unmount();
  expect(signal.aborted).toBe(true);
});

test.each([
  null,
  { currency: "USD", timezone: "Asia/Shanghai", five_hour: {}, weekly: {} },
])(
  "a malformed quota response shows an error instead of loading forever: %j",
  async (response) => {
    getStatsMock.mockResolvedValue(todayStats());
    getQuotaMock.mockResolvedValue(response);
    render(<ComposerUsageChip />);
    fireEvent.click(await screen.findByRole("button", { name: /今日 ¥3\.60/ }));
    expect(
      await screen.findByText("usage.quotaUnavailable"),
    ).toBeInTheDocument();
    expect(screen.queryByText("usage.quotaLoading")).toBeNull();
    expect(screen.getByRole("button", { name: "common.retry" })).toBeEnabled();
  },
);

test.each(["window", "card"])(
  "refreshes immediately when a quota %s expires",
  async (kind) => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-18T00:00:00Z"));
    const quota = {
      currency: "USD",
      timezone: "Asia/Shanghai",
      five_hour: quotaWindow({
        reset_at: kind === "window" ? "2026-10-18T00:00:01Z" : null,
      }),
      weekly: quotaWindow({ reset_at: null }),
      ...(kind === "card"
        ? {
            reset_credits: {
              available_count: 1,
              credits: [
                {
                  id: "expiring-card",
                  status: "available",
                  granted_at: "2026-10-17T00:00:00Z",
                  expires_at: "2026-10-18T00:00:01Z",
                },
              ],
            },
          }
        : {}),
    };
    getStatsMock.mockResolvedValue(todayStats());
    getQuotaMock.mockResolvedValueOnce(quota).mockResolvedValue({
      ...quota,
      five_hour: quotaWindow({ reset_at: null }),
      reset_credits: { available_count: 0, credits: [] },
    });
    const hook = render(<ComposerUsageChip />);
    try {
      await act(async () => {});
      expect(getQuotaMock).toHaveBeenCalledTimes(1);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1500);
      });
      expect(getQuotaMock).toHaveBeenCalledTimes(2);
    } finally {
      hook.unmount();
      vi.useRealTimers();
    }
  },
);

test.each(["window", "card"])(
  "refreshes a %s that expires during delivery once without a stale-response loop",
  async (kind) => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-18T00:00:00Z"));
    const stale = {
      currency: "USD",
      timezone: "Asia/Shanghai",
      five_hour: quotaWindow({
        reset_at: kind === "window" ? "2026-10-18T00:00:01Z" : null,
      }),
      weekly: quotaWindow({ reset_at: null }),
      ...(kind === "card"
        ? {
            reset_credits: {
              available_count: 1,
              credits: [
                {
                  id: "expiring-card",
                  status: "available",
                  granted_at: "2026-10-17T00:00:00Z",
                  expires_at: "2026-10-18T00:00:01Z",
                },
              ],
            },
          }
        : {}),
    };
    let resolveFirst!: (value: unknown) => void;
    getStatsMock.mockResolvedValue(todayStats());
    getQuotaMock
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveFirst = resolve;
          }),
      )
      .mockImplementation(async () => ({ ...stale }));
    const hook = render(<ComposerUsageChip />);
    try {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1500);
        resolveFirst(stale);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(250);
      });
      expect(getQuotaMock).toHaveBeenCalledTimes(2);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });
      expect(getQuotaMock).toHaveBeenCalledTimes(2);
    } finally {
      hook.unmount();
      vi.useRealTimers();
    }
  },
);

test("a failed refresh disables card redemption from the retained snapshot", async () => {
  getStatsMock.mockResolvedValue(todayStats());
  getQuotaMock.mockResolvedValue({
    currency: "USD",
    timezone: "Asia/Shanghai",
    five_hour: quotaWindow({ used_usd: 10, remaining_usd: 0, blocked: true }),
    weekly: quotaWindow(),
    reset_credits: {
      available_count: 1,
      credits: [
        {
          id: "card-one",
          status: "available",
          granted_at: "2026-10-18T00:00:00Z",
          expires_at: "2026-11-17T00:00:00Z",
        },
      ],
    },
  });
  render(<ComposerUsageChip />);
  fireEvent.click(await screen.findByRole("button", { name: /今日 ¥3\.60/ }));
  await waitFor(() => {
    expect(
      screen.getByRole("button", { name: /^usage\.useResetCard \d+$/ }),
    ).toBeEnabled();
  });
  getQuotaMock.mockRejectedValue(new Error("offline"));
  act(() => window.dispatchEvent(new Event("today-usage-refresh")));
  await screen.findByText("usage.quotaUnavailable");
  expect(
    screen.getByRole("button", { name: /^usage\.useResetCard \d+$/ }),
  ).toBeDisabled();
});

test("weekly and five-hour cards have separate actions and target the selected card", async () => {
  getStatsMock.mockResolvedValue(todayStats());
  getQuotaMock.mockResolvedValue({
    currency: "USD",
    timezone: "Asia/Shanghai",
    five_hour: quotaWindow({ used_usd: 1 }),
    weekly: quotaWindow({ used_usd: 1 }),
    reset_credits: {
      available_count: 2,
      credits: [
        {
          id: "five-card",
          window: "five_hour",
          status: "available",
          granted_at: "2026-10-18T00:00:00Z",
          expires_at: "2026-11-17T00:00:00Z",
        },
        {
          id: "week-card",
          window: "weekly",
          status: "available",
          granted_at: "2026-10-18T00:00:00Z",
          expires_at: "2026-11-17T00:00:00Z",
        },
      ],
    },
  });
  consumeCardMock
    .mockRejectedValueOnce(new Error("Lost response"))
    .mockResolvedValue({ outcome: "reset" });
  render(<ComposerUsageChip />);
  fireEvent.click(await screen.findByRole("button", { name: /今日 ¥3\.60/ }));
  await waitFor(() => {
    expect(
      screen.getByRole("button", { name: /^usage\.useFiveHourCard \d+$/ }),
    ).toBeEnabled();
  });
  fireEvent.click(
    screen.getByRole("button", { name: /^usage\.useWeeklyCard \d+$/ }),
  );
  confirmReset();
  await screen.findByText("Lost response");
  expect(
    screen.getByRole("button", { name: /^usage\.useFiveHourCard \d+$/ }),
  ).toBeDisabled();
  fireEvent.click(
    screen.getByRole("button", { name: /^usage\.useWeeklyCard \d+$/ }),
  );
  confirmReset();
  await screen.findByText("usage.resetSuccess");
  expect(consumeCardMock.mock.calls[0]).toEqual(consumeCardMock.mock.calls[1]);
  expect(consumeCardMock).toHaveBeenCalledWith(expect.any(String), "week-card");
});

test("settings presentation shows an empty reset card inventory", async () => {
  getStatsMock.mockResolvedValue(todayStats());
  getQuotaMock.mockResolvedValue({
    currency: "USD",
    timezone: "Asia/Shanghai",
    five_hour: quotaWindow(),
    weekly: quotaWindow(),
    reset_credits: { available_count: 0, credits: [] },
  });
  render(<ComposerUsageChip embedded />);
  expect(
    await screen.findByRole("heading", { name: "usage.quotaTitle" }),
  ).toBeVisible();
  expect(await screen.findAllByRole("progressbar")).toHaveLength(2);
  expect(screen.queryByText("重置卡 0")).toBeNull();
  expect(
    screen.getByRole("region", { name: "usage.resetCardsTitle" }),
  ).toHaveTextContent("usage.resetCardsEmpty");
  expect(screen.queryByRole("button", { name: /今日 ¥3\.60/ })).toBeNull();
  expect(document.getElementById("composer-usage-popover")).toBeNull();
});

test.each([true, false])(
  "reset card inventory is shown only in settings (embedded=%s)",
  async (embedded) => {
    const card = {
      status: "available",
      granted_at: "2026-10-18T00:00:00Z",
      expires_at: "2026-11-17T00:00:00Z",
    };
    getStatsMock.mockResolvedValue(todayStats());
    getQuotaMock.mockResolvedValue({
      currency: "USD",
      timezone: "Asia/Shanghai",
      five_hour: quotaWindow(),
      weekly: quotaWindow(),
      reset_credits: {
        available_count: 3,
        credits: [
          { ...card, id: "weekly", window: "weekly" },
          {
            ...card,
            id: "short",
            window: "five_hour",
            expires_at: "2026-11-01T00:00:00Z",
          },
          { ...card, id: "legacy" },
        ],
      },
    });
    render(<ComposerUsageChip embedded={embedded} />);
    if (!embedded)
      fireEvent.click(
        await screen.findByRole("button", { name: /今日 ¥3\.60/ }),
      );
    await screen.findAllByRole("progressbar");
    const inventory = screen.queryByRole("region", {
      name: "usage.resetCardsTitle",
    });
    if (!embedded) {
      expect(inventory).toBeNull();
      return;
    }
    expect(inventory).toHaveTextContent("usage.resetCardsAvailable");
    expect(inventory).toHaveTextContent("usage.fiveHourCard");
    expect(inventory).toHaveTextContent("usage.weeklyCard");
    expect(inventory).toHaveTextContent("usage.legacyResetCard");
    const table = within(inventory!).getByRole("table", {
      name: "usage.resetCardsTitle",
    });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual([
      "usage.bulkCardsType",
      "usage.resetCardGranted",
      "usage.resetCardExpires",
    ]);
    expect(within(table).getAllByRole("row")).toHaveLength(4);
    expect(within(table).getAllByRole("cell")).toHaveLength(9);
    expect(inventory!.querySelector("time")?.dateTime).toBe(
      "2026-10-18T00:00:00Z",
    );
    expect(inventory!.querySelectorAll("time")[1]?.dateTime).toBe(
      "2026-11-01T00:00:00Z",
    );
    expect(inventory).toHaveTextContent("usage.resetCardUsageHint");
    expect(within(inventory!).queryByText("Asia/Shanghai")).toBeNull();
  },
);

test("header shows only the amount while reset buttons sit beside their quota labels", async () => {
  const card = {
    status: "available",
    granted_at: "2026-10-18T00:00:00Z",
    expires_at: "2026-11-17T00:00:00Z",
  };
  getStatsMock.mockResolvedValue(todayStats());
  const quota = {
    currency: "USD",
    timezone: "Asia/Shanghai",
    five_hour: quotaWindow({ used_usd: 1 }),
    weekly: quotaWindow({ used_usd: 1 }),
    reset_credits: {
      available_count: 3,
      credits: [
        { ...card, id: "short", window: "five_hour" },
        { ...card, id: "week-one", window: "weekly" },
        { ...card, id: "week-two", window: "weekly" },
      ],
    },
  };
  getQuotaMock.mockImplementation(
    () => new Promise((resolve) => setTimeout(() => resolve(quota), 30)),
  );
  render(<ComposerUsageChip />);
  const trigger = await screen.findByRole("button", { name: /今日 ¥3\.60/ });
  await act(async () => {});
  expect(trigger.textContent).toBe("¥3.600");
  expect(trigger.querySelector(".composer-usage-amount")).not.toHaveClass(
    "hidden",
  );
  expect(trigger).not.toHaveAttribute(
    "aria-label",
    expect.stringContaining("usage.resetCardsAvailable"),
  );
  fireEvent.click(trigger);
  await waitFor(() => {
    expect(
      screen.getByRole("button", { name: "usage.useFiveHourCard 1" }),
    ).toBeEnabled();
  });
  expect(
    screen.getByRole("button", { name: "usage.useWeeklyCard 2" }),
  ).toBeEnabled();
  for (const [period, name, count] of [
    ["five_hour", "usage.useFiveHourCard 1", "1"],
    ["weekly", "usage.useWeeklyCard 2", "2"],
  ]) {
    const column = document.querySelector(`[data-period="${period}"]`)!;
    expect(
      within(column as HTMLElement).getByRole("button", { name }),
    ).toHaveTextContent(`common.reset ${count}`);
  }
  expect(screen.queryByText("usage.weeklyResetHint")).toBeNull();
  expect(screen.queryByText("usage.resetCardExpires")).toBeNull();
  expect(screen.queryByText("重置卡 3")).toBeNull();
});

test("committed redemption with a lost response remains retryable after the card disappears", async () => {
  const card = {
    id: "spent-card",
    window: "weekly",
    status: "available",
    granted_at: "2026-10-18T00:00:00Z",
    expires_at: "2026-11-17T00:00:00Z",
  };
  const other = { ...card, id: "kept-card", window: "five_hour" };
  const quota = {
    currency: "USD",
    timezone: "Asia/Shanghai",
    five_hour: quotaWindow({ used_usd: 1 }),
    weekly: quotaWindow({ used_usd: 1 }),
    reset_credits: { available_count: 2, credits: [card, other] },
  };
  getStatsMock.mockResolvedValue(todayStats());
  getQuotaMock.mockResolvedValue(quota);
  consumeCardMock
    .mockRejectedValueOnce(new Error("Lost committed response"))
    .mockResolvedValue({ outcome: "alreadyRedeemed" });
  render(<ComposerUsageChip embedded />);
  const redeem = await screen.findByRole("button", {
    name: /^usage\.useWeeklyCard \d+$/,
  });
  getQuotaMock.mockResolvedValue({
    ...quota,
    five_hour: quotaWindow({ used_usd: 0 }),
    weekly: quotaWindow({ used_usd: 0 }),
    reset_credits: { available_count: 1, credits: [other] },
  });
  fireEvent.click(redeem);
  confirmReset();
  await screen.findByText("Lost committed response");
  expect(
    await screen.findByRole("button", { name: /^usage\.useFiveHourCard \d+$/ }),
  ).toBeDisabled();
  fireEvent.click(await screen.findByRole("button", { name: "common.retry" }));
  await screen.findByText("usage.resetAlreadyRedeemed");
  expect(consumeCardMock.mock.calls[0]).toEqual(consumeCardMock.mock.calls[1]);
});

test.each([true, false])(
  "reset requires confirmation and can be cancelled without consuming a card (embedded=%s)",
  async (embedded) => {
    const card = {
      status: "available",
      granted_at: "2026-10-18T00:00:00Z",
      expires_at: "2026-11-17T00:00:00Z",
    };
    getStatsMock.mockResolvedValue(todayStats());
    getQuotaMock.mockResolvedValue({
      currency: "USD",
      timezone: "Asia/Shanghai",
      five_hour: quotaWindow({ used_usd: 1, unknown: true }),
      weekly: quotaWindow({ used_usd: 1, unknown: true }),
      reset_credits: {
        available_count: 2,
        credits: [
          { ...card, id: "short", window: "five_hour" },
          { ...card, id: "week", window: "weekly" },
        ],
      },
    });
    let finish!: (value: unknown) => void;
    consumeCardMock.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    render(<ComposerUsageChip embedded={embedded} />);
    if (!embedded)
      fireEvent.click(
        await screen.findByRole("button", { name: /今日 ¥3\.60/ }),
      );
    const short = await screen.findByRole("button", {
      name: "usage.useFiveHourCard 1",
    });
    fireEvent.click(short);
    expect(
      screen.getByRole("dialog", { name: "usage.resetConfirmTitle" }),
    ).toHaveTextContent("usage.resetFiveHourConfirm");
    expect(consumeCardMock).not.toHaveBeenCalled();
    const cancel = within(screen.getByRole("dialog")).getByRole("button", {
      name: "common.cancel",
    });
    fireEvent.mouseDown(cancel);
    fireEvent.click(cancel);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(short).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "usage.useWeeklyCard 1" }),
    );
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "usage.resetWeeklyConfirm",
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(short).toBeVisible();
    expect(consumeCardMock).not.toHaveBeenCalled();
    fireEvent.click(short);
    confirmReset();
    expect(consumeCardMock).toHaveBeenCalledWith(expect.any(String), "short");
    expect(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "common.reset",
      }),
    ).toBeDisabled();
    expect(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "common.cancel",
      }),
    ).toBeDisabled();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await act(async () => finish({ outcome: "reset" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("usage.resetSuccess")).toBeVisible();
  },
);

test("embedded quota shows consumed cards even when no cards remain", async () => {
  getStatsMock.mockResolvedValue(todayStats());
  getQuotaMock.mockResolvedValue({
    currency: "USD",
    timezone: "Asia/Shanghai",
    five_hour: quotaWindow(),
    weekly: quotaWindow(),
    reset_credits: {
      available_count: 0,
      credits: [],
      history: [
        {
          id: "used-short",
          window: "five_hour",
          redeemed_at: "2026-10-18T10:00:00Z",
        },
        {
          id: "used-week",
          window: "weekly",
          redeemed_at: "2026-10-18T11:00:00Z",
        },
      ],
    },
  });
  render(<ComposerUsageChip embedded />);
  const log = await screen.findByRole("table", {
    name: "usage.resetCardHistory",
  });
  expect(within(log).getAllByRole("row")).toHaveLength(3);
  expect(within(log).getAllByRole("row")[1]).toHaveTextContent(
    "usage.weeklyCard",
  );
  expect(within(log).getAllByRole("row")[2]).toHaveTextContent(
    "usage.fiveHourCard",
  );
  expect(within(log).getAllByText("usage.resetCardUsed")).toHaveLength(2);
  expect(log.querySelector("time")?.dateTime).toBe("2026-10-18T11:00:00Z");
});

test("card history paginates and shows an empty state after records expire", async () => {
  const { ResetCardHistory } = await import("../ResetCardHistory");
  const history = Array.from({ length: 11 }, (_, index) => ({
    id: `card-${index}`,
    redeemed_at: new Date(Date.UTC(2026, 9, 18, index)).toISOString(),
  }));
  const { rerender } = render(
    <ResetCardHistory history={history} timezone="Asia/Shanghai" />,
  );
  const log = screen.getByRole("table", { name: "usage.resetCardHistory" });
  expect(within(log).getAllByRole("row")).toHaveLength(11);
  fireEvent.click(screen.getByRole("button", { name: "common.next" }));
  expect(within(log).getAllByRole("row")).toHaveLength(2);
  expect(log.querySelector("time")?.dateTime).toBe(history[0].redeemed_at);
  rerender(
    <ResetCardHistory history={history.slice(1)} timezone="Asia/Shanghai" />,
  );
  expect(within(log).getAllByRole("row")).toHaveLength(11);
  rerender(<ResetCardHistory history={history} timezone="Asia/Shanghai" />);
  expect(within(log).getAllByRole("row")).toHaveLength(11);
  expect(log.querySelector("time")?.dateTime).toBe(history[10].redeemed_at);
  rerender(<ResetCardHistory history={[]} timezone="Asia/Shanghai" />);
  expect(screen.getByText("usage.resetCardHistoryEmpty")).toBeInTheDocument();
  expect(screen.queryByRole("table")).toBeNull();
});
