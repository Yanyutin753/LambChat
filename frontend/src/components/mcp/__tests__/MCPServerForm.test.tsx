/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { MCPServerForm } from "../MCPServerForm";
afterEach(cleanup);

test("server fields and added header fields have accessible names", () => {
  render(<MCPServerForm onSave={vi.fn()} onCancel={vi.fn()} />);
  expect(screen.getByLabelText(i18n.t("mcp.form.serverName"))).toBeTruthy();
  expect(
    screen.getByRole("button", { name: i18n.t("mcp.form.transportType") }),
  ).toBeTruthy();
  expect(screen.getByLabelText(i18n.t("mcp.form.url"))).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: i18n.t("mcp.form.add") }));
  expect(
    screen.getByLabelText(i18n.t("mcp.form.headerNamePlaceholder")),
  ).toBeTruthy();
  expect(
    screen.getByLabelText(i18n.t("mcp.form.valuePlaceholder")),
  ).toBeTruthy();
});
