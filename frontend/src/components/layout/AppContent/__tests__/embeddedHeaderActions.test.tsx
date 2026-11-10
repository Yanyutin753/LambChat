/** @vitest-environment jsdom */
import {
  cleanup,
  render,
  screen,
  fireEvent,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useState } from "react";
import { AppShell, type AppShellProps } from "../AppShell";
import { EmbeddedHeaderActionsContext } from "../EmbeddedHeaderActionsContext";
vi.mock("../Header", () => ({ Header: () => <header>Normal header</header> }));
afterEach(cleanup);

test("embedded actions live in the host header once and keep their handlers", () => {
  const click = vi.fn();
  function Host() {
    const [target, setTarget] = useState<HTMLDivElement | null>(null);
    return (
      <EmbeddedHeaderActionsContext.Provider value={target}>
        <header>
          <span>Assistant</span>
          <div ref={setTarget} />
        </header>
        <AppShell
          {...({} as AppShellProps)}
          embedded
          headerActions={<button onClick={click}>Files</button>}
        >
          <main>Conversation</main>
        </AppShell>
      </EmbeddedHeaderActionsContext.Provider>
    );
  }
  const view = render(<Host />);
  const button = within(screen.getByRole("banner")).getByRole("button", {
    name: "Files",
  });
  expect(screen.getAllByRole("button", { name: "Files" })).toHaveLength(1);
  fireEvent.click(button);
  expect(click).toHaveBeenCalledOnce();
  view.unmount();
  expect(screen.queryByText("Files")).toBeNull();
});

test("embedded shell without a host retains its action", () => {
  render(
    <AppShell
      {...({} as AppShellProps)}
      embedded
      headerActions={<button>Files</button>}
    >
      <main>Conversation</main>
    </AppShell>,
  );
  expect(screen.getByRole("button", { name: "Files" })).toBeTruthy();
});
