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

test.each([false, true])(
  "server has only one toggle control (internal: %s)",
  (isInternal) => {
    const onToggle = vi.fn();
    render(
      <MCPServerCard
        server={{
          name: "Research",
          transport: "sse",
          enabled: true,
          is_internal: isInternal,
          is_system: isInternal,
          can_edit: true,
          allowed_roles: [],
          role_quotas: {},
        }}
        onToggle={onToggle}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getAllByRole("switch")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "mcp.card.disable" })).toBeNull();
    expect(
      Boolean(screen.queryByRole("button", { name: "common.moreOptions" })),
    ).toBe(!isInternal);
    fireEvent.click(screen.getByRole("switch"));
    expect(onToggle).toHaveBeenCalledExactlyOnceWith("Research");
  },
);

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
  expect(toggle.textContent).toBe("");
  expect(toggle.classList.contains("scb__action-btn--ghost")).toBe(true);
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

test("server title exposes a native detail action without toggling its state", () => {
  const onClick = vi.fn();
  const onToggle = vi.fn();
  render(
    <MCPServerCard
      server={{
        name: "Research",
        transport: "sse",
        enabled: false,
        is_system: false,
        can_edit: true,
        allowed_roles: [],
        role_quotas: {},
      }}
      onToggle={onToggle}
      onClick={onClick}
    />,
  );
  const title = screen.getByRole("button", { name: "Research" });
  expect(title.getAttribute("type")).toBe("button");
  fireEvent.click(title);
  expect(onClick).toHaveBeenCalledTimes(1);
  expect(onToggle).not.toHaveBeenCalled();
});

test("failed load status renders danger badge with error detail", () => {
  render(
    <MCPServerCard
      server={{
        name: "Broken",
        transport: "streamable_http",
        enabled: true,
        is_system: true,
        can_edit: true,
        allowed_roles: [],
        role_quotas: {},
        last_load_status: "failed",
        consecutive_failures: 7,
        last_load_error: "OSError: connection refused",
      }}
      onToggle={vi.fn()}
    />,
  );
  const badge = screen.getByText("mcp.card.loadFailed");
  expect(badge.classList.contains("scb__status-pill--danger")).toBe(true);
  expect(badge.getAttribute("title")).toContain("connection refused");
});

test("healthy or disabled server shows no load-failure badge", () => {
  const base = {
    name: "Fine",
    transport: "streamable_http",
    is_system: false,
    can_edit: true,
    allowed_roles: [],
    role_quotas: {},
  };
  const { rerender } = render(
    <MCPServerCard
      server={{ ...base, enabled: true, last_load_status: "ok" }}
      onToggle={vi.fn()}
    />,
  );
  expect(screen.queryByText("mcp.card.loadFailed")).toBeNull();
  rerender(
    <MCPServerCard
      server={{ ...base, enabled: false, last_load_status: "failed" }}
      onToggle={vi.fn()}
    />,
  );
  expect(screen.queryByText("mcp.card.loadFailed")).toBeNull();
});

test("retest button reports state and invokes callback without opening the card", () => {
  const server: MCPServerResponse = {
    name: "Broken",
    transport: "streamable_http",
    enabled: true,
    is_system: false,
    can_edit: true,
    allowed_roles: [],
    role_quotas: {},
    last_load_status: "failed",
  };
  const onRetest = vi.fn();
  const onClick = vi.fn();
  const { rerender } = render(
    <MCPServerCard
      server={server}
      onToggle={vi.fn()}
      onRetest={onRetest}
      onClick={onClick}
      retesting={true}
    />,
  );
  const button = screen.getByRole("button", { name: "mcp.card.retest" });
  expect((button as HTMLButtonElement).disabled).toBe(true);
  expect(button.classList.contains("scb__action-btn--ghost")).toBe(true);

  rerender(
    <MCPServerCard
      server={server}
      onToggle={vi.fn()}
      onRetest={onRetest}
      onClick={onClick}
      retesting={false}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "mcp.card.retest" }));
  expect(onRetest).toHaveBeenCalledExactlyOnceWith(server);
  expect(onClick).not.toHaveBeenCalled();
});
