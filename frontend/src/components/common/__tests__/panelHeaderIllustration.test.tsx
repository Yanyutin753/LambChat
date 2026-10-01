/** @vitest-environment jsdom */
import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { PanelHeader } from "../PanelHeader";

afterEach(cleanup);

test("header displays decorative scene artwork in place of the utility icon", () => {
  const { container, getByRole } = render(
    <PanelHeader
      title="角色广场"
      illustration="panel-persona"
      icon={<svg data-testid="utility-icon" />}
    />,
  );
  const artwork = container.querySelector(".panel-header__illustration img");
  expect(artwork?.getAttribute("src")).toBe(
    "/images/illustrations/lamb-panel-persona.png",
  );
  expect(artwork?.getAttribute("alt")).toBe("");
  expect(artwork?.getAttribute("aria-hidden")).toBe("true");
  expect(container.querySelector("svg")).toBeNull();
  expect(getByRole("heading", { name: "角色广场" })).toBeTruthy();
});

test("headers without matching artwork retain their supplied icon", () => {
  const { getByTestId } = render(
    <PanelHeader title="Settings" icon={<svg data-testid="settings-icon" />} />,
  );
  expect(getByTestId("settings-icon")).toBeTruthy();
});
