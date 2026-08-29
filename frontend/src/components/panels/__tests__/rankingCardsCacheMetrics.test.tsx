/** @vitest-environment jsdom */

import { render, screen } from "@testing-library/react";
import { DatabaseZap } from "lucide-react";
import { vi } from "vitest";

import { RankingList } from "../UsagePanel/RankingCards";

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

  expect(screen.getByText("usage.cacheHitRate: 75%")).toBeInTheDocument();
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
