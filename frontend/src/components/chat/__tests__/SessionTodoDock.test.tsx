/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import i18n from "../../../i18n";
import type { Message } from "../../../types";
import { SessionTodoDock } from "../SessionTodoDock";
import {
  PersistentToolPanelHost,
  closeAllPersistentToolPanels,
} from "../ChatMessage/items/persistentToolPanelState";
import {
  resetRightPanelCoordinator,
  collapseRightPanel,
} from "../../common/rightPanelCoordinator";
import { act } from "@testing-library/react";

const messages: Message[] = [
  {
    id: "assistant",
    role: "assistant",
    content: "",
    timestamp: new Date(),
    runId: "run",
    parts: [
      {
        type: "todo",
        items: [
          { content: "Read source", status: "completed" },
          { content: "Verify behavior", status: "in_progress" },
          { content: "Publish", status: "pending" },
        ],
      },
    ],
  },
];

afterEach(() => {
  cleanup();
  closeAllPersistentToolPanels();
  resetRightPanelCoordinator();
});

test("opens the full live checklist from the persistent summary and updates it in place", () => {
  const view = render(
    <>
      <SessionTodoDock running sessionId="s" messages={messages} />
      <PersistentToolPanelHost />
    </>,
  );
  const trigger = screen.getByRole("button", {
    name: i18n.t("chat.todo.openPanel"),
  });
  expect(trigger).toHaveTextContent("Verify behavior");
  fireEvent.click(trigger);
  expect(screen.getByRole("tabpanel")).toHaveTextContent("Publish");
  const panelId = screen.getByRole("tab").getAttribute("aria-controls");
  const done: Message[] = [
    {
      ...messages[0],
      parts: [
        {
          type: "todo",
          items: [
            { content: "Read source", status: "completed" },
            { content: "Verify behavior", status: "completed" },
            { content: "Publish", status: "cancelled" },
          ],
        },
      ],
    },
  ];
  view.rerender(
    <>
      <SessionTodoDock running sessionId="s" messages={done} />
      <PersistentToolPanelHost />
    </>,
  );
  expect(screen.getByRole("tab").getAttribute("aria-controls")).toBe(panelId);
  expect(screen.getByRole("tabpanel")).toHaveTextContent(
    i18n.t("chat.todo.cancelled"),
  );
  expect(trigger).not.toHaveTextContent("Verify behavior");
  act(() => collapseRightPanel());
  fireEvent.click(trigger);
  expect(screen.getByRole("tabpanel")).toHaveTextContent("Publish");
  view.rerender(
    <>
      <SessionTodoDock running sessionId="other" messages={[]} />
      <PersistentToolPanelHost />
    </>,
  );
  expect(screen.queryByRole("tabpanel")).toBeNull();
  expect(
    screen.queryByRole("button", { name: i18n.t("chat.todo.openPanel") }),
  ).toBeNull();
});

test("the dock never opens a panel automatically", () => {
  render(
    <>
      <SessionTodoDock running sessionId="s" messages={messages} />
      <PersistentToolPanelHost />
    </>,
  );
  expect(screen.queryByRole("tabpanel")).toBeNull();
});

test("completed task summary stays compact and the checklist avoids repeating its header", () => {
  const done: Message[] = [
    {
      ...messages[0],
      parts: [
        {
          type: "todo",
          items: [{ content: "Read source", status: "completed" }],
        },
      ],
    },
  ];
  render(
    <>
      <SessionTodoDock running sessionId="s" messages={done} />
      <PersistentToolPanelHost />
    </>,
  );
  const trigger = screen.getByRole("button", {
    name: i18n.t("chat.todo.openPanel"),
  });
  expect(trigger).toHaveClass("w-full", "min-h-11");
  expect(trigger).not.toHaveTextContent(i18n.t("chat.todo.allCompleted"));
  fireEvent.click(trigger);
  const panel = screen.getByRole("tabpanel");
  expect(panel).not.toHaveTextContent(
    i18n.t("chat.todo.progress", { completed: 1, total: 1 }),
  );
  expect(panel.querySelector("ul")?.parentElement).toHaveClass("px-4", "py-4");
});

test("finishing the conversation hides the summary and closes its open checklist", () => {
  const view = render(
    <>
      <SessionTodoDock running sessionId="s" messages={messages} />
      <PersistentToolPanelHost />
    </>,
  );
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("chat.todo.openPanel") }),
  );
  expect(screen.getByRole("tabpanel")).toBeInTheDocument();
  view.rerender(
    <>
      <SessionTodoDock running={false} sessionId="s" messages={messages} />
      <PersistentToolPanelHost />
    </>,
  );
  expect(
    screen.queryByRole("button", { name: i18n.t("chat.todo.openPanel") }),
  ).toBeNull();
  expect(screen.queryByRole("tabpanel")).toBeNull();
});
