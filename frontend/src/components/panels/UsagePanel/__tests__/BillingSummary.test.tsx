/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { BillingSummary } from "../BillingSummary";
import type { UsageStats } from "../../../../types/usage";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, args?: { count?: number }) =>
      `${key}${args?.count === undefined ? "" : ` ${args.count}`}`,
    i18n: { language: "en" },
  }),
}));
vi.mock("../../../../hooks/useFxRates", () => ({ useFxRates: () => null }));
vi.mock("recharts", () => ({
  ResponsiveContainer: () => null,
  BarChart: () => null,
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));
afterEach(cleanup);
const stats = {
  total_requests: 5722,
  total_cost_usd: 98.05,
  partial_cost_usd: 112.56,
  priced_requests: 4060,
  partial_requests: 352,
  unpriced_requests: 20,
  estimated_cost_usd: 7,
  estimated_requests: 1,
} as UsageStats;
test("separates known charges from historical estimates and labels the successful-request denominator", () => {
  render(<BillingSummary stats={stats} />);
  expect(screen.getByText("$98.05")).toBeTruthy();
  expect(screen.getByText("$112.56")).toBeTruthy();
  expect(screen.getByText(/≈\$7.00/)).toBeTruthy();
  expect(screen.getByText("usage.billing.coverageScope")).toBeTruthy();
  expect(screen.getByText("usage.billing.unpriced 20")).toBeTruthy();
  expect(screen.queryByText("$217.61")).toBeNull();
});
test("missing receipt amounts stay unknown instead of displaying free usage", () => {
  render(<BillingSummary stats={{ total_requests: 1 } as UsageStats} />);
  expect(screen.queryByText("$0.00")).toBeNull();
  expect(screen.getAllByText("—")).toHaveLength(2);
});
