/** @vitest-environment jsdom */
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { UsagePanel } from "../UsagePanel";
import { TODAY_USAGE_REFRESH_EVENT } from "../../../hooks/useTodayUsageCost";

const state = vi.hoisted(() => ({ tokens: 123, models: [], agents: [] }));
vi.mock("react-i18next", () => ({
  initReactI18next: { type: "3rdParty", init() {} },
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../../hooks/useFxRates", () => ({ useFxRates: () => null }));
vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasPermission: () => false }),
}));
vi.mock("../../../contexts/SettingsContext", () => ({
  useSettingsContext: () => ({ availableModels: state.models }),
}));
vi.mock("../../agent/useAgentCatalog", () => ({
  useAgentCatalog: () => state.agents,
}));
vi.mock("../../../services/api/usage", () => ({
  usageApi: {
    list: async () => ({
      total: 1,
      stats: null,
      items: [
        {
          trace_id: "trace",
          status: "running",
          model: "model",
          input_tokens: state.tokens,
          output_tokens: 10,
          total_tokens: state.tokens + 10,
          cache_read_tokens: 0,
          cache_creation_tokens: 0,
          usage_incomplete: false,
          unknown_usage_fields: [],
        },
      ],
    }),
    getDashboard: async () => null,
  },
}));
afterEach(cleanup);

test("an open usage panel refreshes the running row on a usage notification", async () => {
  render(<UsagePanel />);
  expect(await screen.findAllByText("123")).toHaveLength(3);
  state.tokens = 456;
  act(() => window.dispatchEvent(new Event(TODAY_USAGE_REFRESH_EVENT)));
  expect(await screen.findAllByText("456")).toHaveLength(3);
  expect(screen.queryAllByText("123")).toHaveLength(0);
});
