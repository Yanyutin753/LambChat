/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Bot } from "lucide-react";
import type { UsageRankingItem } from "../../../../types/usage";
import { RankingList, DistributionList } from "../RankingCards";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { count?: string | number }) =>
      opts?.count === undefined ? key : `${key}: ${opts.count}`,
    i18n: { language: "en" },
  }),
}));
vi.mock("../../../../hooks/useFxRates", () => ({ useFxRates: () => null }));
afterEach(cleanup);
const item = {
  id: "search",
  name: "Search",
  requests: 2,
  tokens: 0,
  input_tokens: 0,
  cache_read_tokens: 42,
  cache_creation_tokens: 0,
  cache_read_share: null,
  zero_cache_requests: 0,
  duration: 1,
  unknown_usage_fields: [
    "input_tokens",
    "total_tokens",
    "cache_creation_tokens",
  ],
} satisfies UsageRankingItem;

test("ranking reports known reads while unknown summed tokens stay unknown", () => {
  render(
    <RankingList
      title="Agents"
      icon={Bot}
      items={[item]}
      emptyLabel="Empty"
      showCacheMetrics
    />,
  );
  expect(screen.getByText("—")).toBeInTheDocument();
  expect(screen.getByText("usage.cacheRead: 42")).toBeInTheDocument();
  expect(screen.queryByText("0")).toBeNull();
});

test("distribution does not report an unknown aggregate token sum as zero", () => {
  render(
    <DistributionList
      title="Sources"
      icon={Bot}
      items={[item]}
      total={2}
      emptyLabel="Empty"
    />,
  );
  expect(screen.getByText("usage.ranking.tokensValue: —")).toBeInTheDocument();
});

test("ranking retains a positive reported subtotal when another call is unknown", () => {
  render(
    <RankingList
      title="Agents"
      icon={Bot}
      items={[{ ...item, tokens: 2400 }]}
      emptyLabel="Empty"
    />,
  );
  expect(screen.getByText("2.4K")).toBeInTheDocument();
});
