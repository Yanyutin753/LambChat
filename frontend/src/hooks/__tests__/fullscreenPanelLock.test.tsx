/** @vitest-environment jsdom */
import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { useBodyScrollLock } from "../useBodyScrollLock";

afterEach(cleanup);

function Lock({ fullscreen = false }: { fullscreen?: boolean }) {
  useBodyScrollLock(true, true, fullscreen);
  return null;
}

test("nested fullscreen viewers keep the side panel inert until the last viewer closes", () => {
  const panel = document.createElement("div");
  panel.setAttribute("data-right-panel-root", "true");
  document.body.append(panel);
  const modal = render(<Lock />);
  const first = render(<Lock fullscreen />);
  const second = render(<Lock fullscreen />);
  try {
    expect(panel.inert).toBe(true);
    first.unmount();
    expect(panel.inert).toBe(true);
    second.unmount();
    expect(panel.inert).toBe(false);
  } finally {
    modal.unmount();
    panel.remove();
  }
});
