/** @vitest-environment jsdom */

import { render, screen, within } from "@testing-library/react";
import { DatabaseZap } from "lucide-react";
import { vi } from "vitest";

import { RankingList } from "../UsagePanel/RankingCards";
import { InsightStrip } from "../UsagePanel/InsightStrip";
import type { UsageDashboardResponse } from "../../../types/usage";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number; n?: number }) =>
      options?.count ?? options?.n ?? key,
    i18n: { language: "en" },
  }),
  initReactI18next: { type: "3rdParty", init: () => {} },
}));

const modelItem = {
  id: "deepseek-v4-flash",
  name: "DeepSeek V4 Flash",
  requests: 3,
  tokens: 2400,
  duration: 9.5,
  input_tokens: 2000,
  cache_creation_tokens: 100,
  cache_read_tokens: 1500,
  cache_read_share: 0.75,
  zero_cache_requests: 1,
};

test("shows cache metrics when the ranking opts in", () => {
  render(
    <RankingList
      title="Models"
      icon={DatabaseZap}
      items={[modelItem]}
      emptyLabel="Empty"
      showCacheMetrics
    />,
  );

  expect(screen.getByText("usage.cacheHitRate: 75.0%")).toBeInTheDocument();
  expect(screen.getByText("usage.cacheRead: 1.5K")).toBeInTheDocument();
});

test("keeps cache metrics hidden for ordinary rankings", () => {
  render(
    <RankingList
      title="Agents"
      icon={DatabaseZap}
      items={[modelItem]}
      emptyLabel="Empty"
    />,
  );

  expect(screen.queryByText(/usage\.cacheHitRate/)).not.toBeInTheDocument();
  expect(screen.queryByText(/usage\.cacheRead/)).not.toBeInTheDocument();
});

test("ranking omits missing-data disclaimers while explicit zero stays zero", () => {
  const { rerender } = render(
    <RankingList
      title="Models"
      icon={DatabaseZap}
      items={[{ ...modelItem, cache_read_share: null }]}
      emptyLabel="Empty"
      showCacheMetrics
    />,
  );
  expect(screen.queryByText("usage.cacheRateUnknown")).not.toBeInTheDocument();
  rerender(
    <RankingList
      title="Models"
      icon={DatabaseZap}
      items={[{ ...modelItem, cache_read_share: 0 }]}
      emptyLabel="Empty"
      showCacheMetrics
    />,
  );
  expect(screen.getByText("usage.cacheHitRate: 0.0%")).toBeVisible();
  expect(screen.queryByText("usage.cacheRateUnknown")).not.toBeInTheDocument();
});

test("cache insight omits missing-data disclaimers", () => {
  const dashboard = (rate: number | null) =>
    ({
      summary: {
        peak_day: null,
        failed_requests: 0,
        cancelled_requests: 0,
        success_rate: 1,
        avg_tokens_per_request: 100,
        avg_duration_per_request: 1,
        scheduled_share: 0,
        scheduled_runs: 0,
        cache_read_share: rate,
        total_cache_read_tokens: 0,
        max_duration: 1,
        tool_calls_per_request: 0,
      },
    }) as UsageDashboardResponse;
  const { rerender } = render(<InsightStrip dashboard={dashboard(null)} />);
  const insight = screen.getByText("usage.insight.cacheReuse").parentElement!
    .parentElement!;
  expect(within(insight).getByText("—")).toBeVisible();
  expect(
    within(insight).queryByText(/usage\.cacheRateUnknown/),
  ).not.toBeInTheDocument();
  rerender(<InsightStrip dashboard={dashboard(0)} />);
  expect(within(insight).getByText("0.0%")).toBeVisible();
  expect(within(insight).getByText("0")).toBeVisible();
  expect(
    within(insight).queryByText(/usage\.cacheRateUnknown/),
  ).not.toBeInTheDocument();
});
