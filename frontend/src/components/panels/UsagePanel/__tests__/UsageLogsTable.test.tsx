/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { UsageLog } from "../../../../types/usage";
import { UsageLogsTable } from "../UsageLogsTable";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en" },
  }),
}));
vi.mock("../../../../hooks/useFxRates", () => ({ useFxRates: () => null }));
afterEach(cleanup);

test("running usage is labelled as running in every responsive layout", () => {
  show({ status: "running" });
  expect(screen.getAllByText("usage.statusRunning")).toHaveLength(3);
  expect(screen.queryByText("usage.statusError")).toBeNull();
});

function show(overrides: Partial<UsageLog> = {}, hasAnyCache = false) {
  const log = {
    trace_id: "trace",
    session_id: "session",
    user_id: "owner",
    username: "Owner",
    agent_name: "Search",
    model: "model",
    duration: 1.5,
    input_tokens: 456,
    output_tokens: 789,
    total_tokens: 1245,
    usage_incomplete: true,
    unknown_usage_fields: ["input_tokens", "total_tokens"],
    status: "cancelled",
    started_at: null,
    completed_at: null,
    ...overrides,
  } as UsageLog;
  render(
    <UsageLogsTable
      logs={[log]}
      total={1}
      page={1}
      pageSize={20}
      isAdmin={false}
      hasAnyCache={hasAnyCache}
    />,
  );
}

test("unknown counters stay unknown in desktop, tablet and mobile layouts", () => {
  show();
  expect(screen.queryAllByText("456")).toHaveLength(0);
  expect(screen.queryAllByText("1.2K")).toHaveLength(0);
  expect(screen.getAllByText("789")).toHaveLength(3);
});

test("measured zero survives and legacy incomplete values remain unknown", () => {
  show({
    input_tokens: 0,
    output_tokens: 321,
    total_tokens: 321,
    usage_incomplete: false,
    unknown_usage_fields: [],
  });
  expect(screen.getAllByText("0")).toHaveLength(3);
  cleanup();
  show({ unknown_usage_fields: undefined });
  expect(screen.queryAllByText("456")).toHaveLength(0);
  expect(screen.queryAllByText("789")).toHaveLength(0);
});

test("historical estimates are labelled in every responsive layout", () => {
  show({ cost_available: false, estimated_cost_usd: 0.4 });
  expect(screen.getAllByText("≈$0.4")).toHaveLength(3);
  expect(screen.getAllByText(/usage.historicalEstimate/)).toHaveLength(3);
});
test("partial zero remains visible alongside a separate historical estimate", () => {
  show({ cost_available: false, partial_cost_usd: 0, estimated_cost_usd: 0.4 });
  expect(screen.getAllByText("$0.00+")).toHaveLength(3);
  expect(screen.getAllByText(/usage.historicalEstimate/)).toHaveLength(3);
});

test("known cache reads remain reportable even when cache writes and ratios are incomplete", () => {
  show(
    {
      cache_read_tokens: 321,
      cache_metrics_available: false,
      unknown_usage_fields: ["cache_creation_tokens"],
    },
    true,
  );
  expect(screen.getAllByText("321")).toHaveLength(3);
});

test("legacy null completeness reports valid counts and labels its estimate while explicit incomplete stays unknown", () => {
  const legacy: Partial<UsageLog> = {
    usage_incomplete: null,
    unknown_usage_fields: [],
    cache_read_tokens: 321,
    cost_available: false,
    estimated_cost_usd: 0.4,
  };
  show(legacy, true);
  for (const count of ["456", "789", "321", "1.2K"]) {
    expect(screen.getAllByText(count)).toHaveLength(3);
  }
  expect(screen.getAllByText("≈$0.4")).toHaveLength(3);
  expect(screen.getAllByText(/usage.historicalEstimate/)).toHaveLength(3);
  cleanup();
  show({ ...legacy, usage_incomplete: true }, true);
  for (const count of ["456", "789", "321", "1.2K"]) {
    expect(screen.queryAllByText(count)).toHaveLength(0);
  }
  expect(screen.getAllByText("≈$0.4")).toHaveLength(3);
});

test("auxiliary calls remain identifiable across responsive layouts", () => {
  show({ source: "auxiliary", agent_name: "" });
  expect(screen.getAllByText("usage.sources.auxiliary")).toHaveLength(3);
});
