/** @vitest-environment jsdom */
import { useRef, useState } from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { I18nextProvider } from "react-i18next";
import i18n from "../../../i18n";
import { AgentModeSelector } from "../AgentModeSelector";

afterEach(cleanup);
test("an initially unavailable mode catalog stays open through retry and keeps focus while options recover", async () => {
  const select = vi.fn();
  let finish!: () => void;
  const pending = new Promise<void>((resolve) => {
    finish = resolve;
  });
  function Picker() {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(true);
    const [agents, setAgents] = useState<
      { id: string; name: string; description: string }[]
    >([]);
    const [open, setOpen] = useState(true);
    return (
      <AgentModeSelector
        agents={agents}
        currentAgent="search"
        isLoading={loading}
        error={error}
        isOpen={open}
        onOpenChange={setOpen}
        onSelectAgent={select}
        onRetry={() => {
          setLoading(true);
          pending.then(() => {
            setAgents([
              {
                id: "search",
                name: "Research mode",
                description: "Check sources",
              },
            ]);
            setLoading(false);
            setError(false);
          });
        }}
      />
    );
  }
  render(
    <I18nextProvider i18n={i18n.cloneInstance({ lng: "zh" })}>
      <Picker />
    </I18nextProvider>,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("加载失败");
  expect(screen.queryByText("未找到结果")).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "重试: 选择模式" }));
  const focused = document.activeElement;
  expect(focused).not.toBe(document.body);
  expect(focused).toHaveAttribute("tabindex", "-1");
  expect(screen.getByRole("status")).toHaveTextContent("加载中");
  await act(async () => finish());
  expect(document.activeElement).toBe(focused);
  expect(focused?.isConnected).toBe(true);
  await userEvent.click(screen.getByRole("button", { name: /搜索助手/ }));
  expect(select).toHaveBeenCalledWith("search");
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("a successful empty catalog remains visible and its close action returns to the opener", async () => {
  function Picker() {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLButtonElement>(null);
    return (
      <>
        <button ref={ref} onClick={() => setOpen(true)}>
          Modes
        </button>
        <AgentModeSelector
          agents={[]}
          currentAgent=""
          isOpen={open}
          onOpenChange={setOpen}
          onSelectAgent={vi.fn()}
        />
      </>
    );
  }
  render(
    <I18nextProvider i18n={i18n.cloneInstance({ lng: "zh" })}>
      <Picker />
    </I18nextProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Modes" }));
  expect(screen.getByText("未找到结果")).toBeVisible();
  await userEvent.keyboard("{Escape}");
  expect(screen.getByRole("button", { name: "Modes" })).toHaveFocus();
});
