/** @vitest-environment jsdom */
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { PersonaAvatarWithLoading } from "../PersonaAvatarWithLoading";
import { PersonaAvatarIcon } from "../PersonaAvatarIcon";
import type { PersonaPreset } from "../../../types";

afterEach(cleanup);

test("a role without an avatar gets the local lamb with a local error fallback", () => {
  const preset = { name: "Research", tags: [] } as unknown as PersonaPreset;
  const { container } = render(<PersonaAvatarWithLoading preset={preset} />);
  const image = container.querySelector("img");
  expect(image?.getAttribute("src")).toBe(
    "/images/illustrations/lamb-avatar.png",
  );
  fireEvent.error(image!);
  expect(container.querySelector("svg")).not.toBeNull();
});

test("default role icons use the same lamb even when a category is present", () => {
  const { container } = render(<PersonaAvatarIcon primaryTag="coding" />);
  expect(container.querySelector("img")?.getAttribute("src")).toBe(
    "/images/illustrations/lamb-avatar.png",
  );
});

test("the default lamb fills the same image frame as uploaded avatars", () => {
  const preset = { name: "Research", tags: [] } as unknown as PersonaPreset;
  const { container } = render(
    <PersonaAvatarWithLoading
      preset={preset}
      iconSize={22}
      imgClassName="h-full w-full object-cover"
    />,
  );
  const image = container.querySelector("img");
  expect(image?.style.width).toBe("100%");
  expect(image?.style.height).toBe("100%");
  expect(image?.parentElement).toHaveClass("h-full", "w-full");
});

test("an explicit uploaded avatar keeps its source", () => {
  const preset = {
    name: "Research",
    tags: [],
    avatar: "https://example.com/me.png",
  } as unknown as PersonaPreset;
  const { container } = render(<PersonaAvatarWithLoading preset={preset} />);
  expect(container.querySelector("img")?.src).toBe(preset.avatar);
});
