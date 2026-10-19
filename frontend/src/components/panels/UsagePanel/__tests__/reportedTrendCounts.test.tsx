/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { ReactNode } from "react";
import { MiniTrend } from "../MiniTrend";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => children,
  AreaChart: ({ data }: { data: unknown }) => (
    <div data-testid="chart-data">{JSON.stringify(data)}</div>
  ),
  Area: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ReferenceDot: () => null,
}));
afterEach(cleanup);

test("daily trend leaves unknown token observations unplotted and its total unknown", () => {
  render(
    <MiniTrend
      points={[
        {
          date: "2026-10-18",
          requests: 2,
          tokens: 0,
          duration: 1,
          scheduled_runs: 0,
          failed_requests: 0,
          tool_calls: 0,
          unknown_usage_fields: ["total_tokens"],
        },
      ]}
    />,
  );
  const data = JSON.parse(screen.getByTestId("chart-data").textContent!);
  expect(
    data.find((point: { date: string }) => point.date === "10/18").Tokens,
  ).toBeNull();
  expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
});

test("daily trend plots available subtotal despite an incomplete call", () => {
  render(
    <MiniTrend
      points={[
        {
          date: "2026-10-18",
          requests: 2,
          tokens: 2400,
          duration: 1,
          scheduled_runs: 0,
          failed_requests: 0,
          tool_calls: 0,
          unknown_usage_fields: ["total_tokens"],
        },
      ]}
    />,
  );
  const data = JSON.parse(screen.getByTestId("chart-data").textContent!);
  expect(
    data.find((point: { date: string }) => point.date === "10/18").Tokens,
  ).toBe(2400);
});
