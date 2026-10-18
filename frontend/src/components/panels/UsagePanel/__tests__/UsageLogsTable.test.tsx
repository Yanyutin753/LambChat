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

function show(overrides: Partial<UsageLog> = {}) {
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
      hasAnyCache={false}
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
