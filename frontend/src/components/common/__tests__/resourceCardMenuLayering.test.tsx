/** @vitest-environment jsdom */
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ResourceCardMenu } from "../ResourceCardMenu";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);

function renderMenu(onClose: ReturnType<typeof vi.fn>) {
  render(
    <ResourceCardMenu
      id="layering-menu"
      title="Actions"
      position={{ x: 0, y: 0 }}
      onClose={onClose}
      actions={[{ label: "Edit", onClick: vi.fn() }]}
    />,
  );
}

test("menu keeps Escape when it owns the focus", () => {
  const close = vi.fn();
  renderMenu(close);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(close).toHaveBeenCalledWith(true);
});

test("menu yields Escape to a newer foreground dialog holding focus", () => {
  const close = vi.fn();
  renderMenu(close);
  // A newer overlay opens and takes focus: the menu must not intercept.
  const dialog = document.createElement("div");
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  const dialogButton = document.createElement("button");
  dialogButton.textContent = "In dialog";
  dialog.append(dialogButton);
  document.body.append(dialog);
  dialogButton.focus();

  const handledElsewhere = vi.fn();
  document.addEventListener("keydown", handledElsewhere);

  fireEvent.keyDown(document, { key: "Escape" });
  expect(close).not.toHaveBeenCalled();
  expect(handledElsewhere).toHaveBeenCalled();

  dialog.remove();
  document.removeEventListener("keydown", handledElsewhere);
});
