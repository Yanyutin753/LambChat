/** @vitest-environment jsdom */
import { afterEach, expect, test, vi } from "vitest";
import { waitFor } from "@testing-library/react";
import { observePanelWidths } from "../panelWidths";

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

test.each([
  "panel-body overflow-y-auto",
  "panel-scroll",
  "editor-sidebar-body",
])(
  "%s keeps header width aligned across mount, resize and removal",
  async (className) => {
    let resize: () => void = () => {};
    const disconnect = vi.fn();
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(callback: () => void) {
          resize = callback;
        }
        observe() {}
        unobserve() {}
        disconnect = disconnect;
      },
    );
    const root = document.createElement("main");
    root.innerHTML = "<section><header></header></section>";
    document.body.append(root);
    const stop = observePanelWidths(root);
    const scope = root.firstElementChild as HTMLElement;
    const body = document.createElement("div");
    body.className = className;
    Object.defineProperty(body, "offsetWidth", { value: 400 });
    Object.defineProperty(body, "clientWidth", {
      configurable: true,
      value: 389,
    });
    scope.append(body);
    await waitFor(() =>
      expect(scope.style.getPropertyValue("--panel-scrollbar")).toBe("11px"),
    );
    Object.defineProperty(body, "clientWidth", {
      configurable: true,
      value: 400,
    });
    resize();
    expect(scope.style.getPropertyValue("--panel-scrollbar")).toBe("0px");
    body.remove();
    await waitFor(() =>
      expect(scope.style.getPropertyValue("--panel-scrollbar")).toBe(""),
    );
    stop();
    expect(disconnect).toHaveBeenCalled();
  },
);

test("nested panel chrome shares the scroll gutter with its outer hub header", () => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  const root = document.createElement("main");
  root.innerHTML =
    '<section><header></header><div><div class="panel-body overflow-y-auto"></div></div></section>';
  document.body.append(root);
  const body = root.querySelector(".panel-body")!;
  Object.defineProperty(body, "offsetWidth", { value: 400 });
  Object.defineProperty(body, "clientWidth", { value: 389 });
  const stop = observePanelWidths(root);
  expect(root.style.getPropertyValue("--panel-scrollbar")).toBe("11px");
  stop();
  expect(root.style.getPropertyValue("--panel-scrollbar")).toBe("");
});
