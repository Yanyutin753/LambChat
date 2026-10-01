/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MCPServerCard } from "../MCPServerCard";
import type { MCPServerResponse } from "../../../types";

vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);

test("server switch exposes its state and toggles without opening the card", () => {
  const server: MCPServerResponse = {
    name: "Research",
    transport: "sse",
    enabled: false,
    is_system: false,
    can_edit: true,
    allowed_roles: [],
    role_quotas: {},
  };
  const onToggle = vi.fn();
  const onClick = vi.fn();
  const { rerender } = render(
    <MCPServerCard server={server} onToggle={onToggle} onClick={onClick} />,
  );
  const toggle = screen.getByRole("switch", { name: "mcp.card.enable" });
  expect(toggle.getAttribute("aria-checked")).toBe("false");
  fireEvent.click(toggle);
  expect(onToggle).toHaveBeenCalledWith("Research");
  expect(onClick).not.toHaveBeenCalled();
  rerender(
    <MCPServerCard
      server={{ ...server, enabled: true }}
      onToggle={onToggle}
      onClick={onClick}
    />,
  );
  expect(
    screen
      .getByRole("switch", { name: "mcp.card.disable" })
      .getAttribute("aria-checked"),
  ).toBe("true");
});
