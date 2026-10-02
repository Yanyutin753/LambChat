/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SelectorModalHeader } from "../shared/SelectorModalHeader";
import i18n from "../../../i18n";

afterEach(cleanup);
test("shared selector close is a named native button with a full touch target", () => {
  const close = vi.fn();
  render(<SelectorModalHeader title="Mode" icon={<span />} onClose={close} />);
  const button = screen.getByRole("button", { name: i18n.t("common.close") });
  expect(button.getAttribute("type")).toBe("button");
  expect(button.className).toContain("size-11");
  fireEvent.click(button);
  expect(close).toHaveBeenCalledOnce();
});
