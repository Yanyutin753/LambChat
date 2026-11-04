/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AssistantRulesDialog } from "../AssistantRulesDialog";
import type { Assistant } from "../../../types/assistant";
const { api, schedule, navigate, t } = vi.hoisted(() => ({
  api: { rules: vi.fn(), createRule: vi.fn() },
  schedule: { update: vi.fn(), resume: vi.fn() },
  navigate: vi.fn(),
  t: (key: string) => key,
}));
vi.mock("../../../services/api/assistant", () => ({ assistantApi: api }));
vi.mock("../../../services/api/scheduledTask", () => ({
  scheduledTaskApi: schedule,
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t }) }));
const assistant = {
  id: "helper",
  name: "Researcher",
  status: "active",
} as Assistant;
beforeEach(() => {
  api.rules.mockResolvedValue({ rules: [], total: 0 });
});

test("rule pagination retains its total between pages", async () => {
  api.rules.mockImplementation((_id, skip) =>
    Promise.resolve({
      total: 11,
      rules: [
        {
          id: "rule",
          name: skip ? "Second page" : "First page",
          enabled: false,
          status: "paused",
          trigger_type: "interval",
          trigger_config: { seconds: 300 },
          input_payload: {
            message: "Check",
            assistant_rule: {
              assistant_id: "helper",
              mode: "observe",
              timeout_seconds: 120,
              max_wakeups: 3,
            },
          },
        },
      ],
    }),
  );
  render(
    <AssistantRulesDialog
      assistant={assistant}
      canWrite={false}
      onClose={() => {}}
    />,
  );
  await screen.findByText("First page");
  fireEvent.click(screen.getByRole("button", { name: "common.next" }));
  expect(await screen.findByText("Second page")).toBeVisible();
  expect(api.rules).toHaveBeenLastCalledWith("helper", 10, 10);
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

test("new rules default to observation and submit bounded parameters", async () => {
  api.createRule.mockResolvedValue({ id: "rule" });
  render(
    <AssistantRulesDialog assistant={assistant} canWrite onClose={() => {}} />,
  );
  fireEvent.change(screen.getByLabelText("assistants.ruleName"), {
    target: { value: "Research changes" },
  });
  fireEvent.change(screen.getByLabelText("assistants.ruleInstructions"), {
    target: { value: "Check the documented sources" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "assistants.createRule" }),
  );
  await waitFor(() =>
    expect(api.createRule).toHaveBeenCalledWith(
      "helper",
      expect.objectContaining({
        mode: "observe",
        timeout_seconds: 300,
        max_wakeups: 10,
        interval_seconds: 3600,
      }),
    ),
  );
});

test("readers see wakeup budget and actual admission state without write controls", async () => {
  api.rules.mockResolvedValue({
    total: 1,
    rules: [
      {
        id: "rule",
        name: "Research",
        enabled: true,
        status: "active",
        trigger_type: "interval",
        trigger_config: { seconds: 300 },
        input_payload: {
          message: "Check",
          assistant_rule: {
            assistant_id: "helper",
            mode: "auto",
            timeout_seconds: 120,
            max_wakeups: 3,
          },
        },
        assistant_rule_wakeups: 2,
        assistant_rule_last_claim: { status: "admitting" },
      },
    ],
  });
  render(
    <AssistantRulesDialog
      assistant={assistant}
      canWrite={false}
      onClose={() => {}}
    />,
  );
  await screen.findByText("Research");
  expect(
    screen.getByText("assistants.ruleClaimStates.admitting"),
  ).toBeInTheDocument();
  expect(screen.getByText("assistants.ruleBudget")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "assistants.createRule" }),
  ).toBeNull();
  fireEvent.click(
    screen.getByRole("button", { name: "assistants.ruleHistory" }),
  );
  expect(navigate).toHaveBeenCalledWith("/scheduled-tasks/rule");
});
