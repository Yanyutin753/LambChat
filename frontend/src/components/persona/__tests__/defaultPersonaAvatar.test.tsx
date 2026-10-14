/** @vitest-environment jsdom */
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { PersonaAvatarWithLoading } from "../PersonaAvatarWithLoading";
import { PersonaAvatarIcon } from "../PersonaAvatarIcon";
import type { PersonaPreset } from "../../../types";

afterEach(cleanup);

test("a role without an avatar gets a local color avatar", () => {
  const preset = { id: "research", name: "Research", tags: [] } as unknown as PersonaPreset;
  const { container } = render(<PersonaAvatarWithLoading preset={preset} />);
  expect(container.querySelector("[data-avatar-style=boring]")).not.toBeNull();
  expect(container.querySelector("img")).toBeNull();
});

test("the fallback fills the same frame as uploaded avatars", () => {
  const preset = { name: "Research", tags: [] } as unknown as PersonaPreset;
  const { container } = render(<PersonaAvatarWithLoading preset={preset} imgClassName="h-full w-full object-cover" />);
  const frame = container.querySelector("[data-avatar-style=boring]") as HTMLElement | null;
  expect(frame?.style.width).toBe("100%");
  expect(frame?.style.height).toBe("100%");
});

test("an explicit uploaded avatar keeps its source and falls back locally on error", () => {
  const preset = { name: "Research", tags: [], avatar: "https://example.com/me.png" } as unknown as PersonaPreset;
  const { container } = render(<PersonaAvatarWithLoading preset={preset} />);
  const image = container.querySelector("img");
  expect(image?.src).toBe(preset.avatar);
  fireEvent.error(image!);
  expect(container.querySelector("[data-avatar-style=boring]")).not.toBeNull();
});

test("a saved generated avatar is identical on the role card and icon surface", () => {
  const preset = { name: "Research", tags: [], avatar: "generated:avatar-3" } as unknown as PersonaPreset;
  const { container, rerender } = render(<PersonaAvatarWithLoading preset={preset} />);
  const paths = () => {
    const frame = container.querySelector("[data-avatar-style=boring]") as HTMLElement | null;
    return [frame?.style.background, frame?.style.borderRadius];
  };
  const first = paths();
  rerender(<PersonaAvatarIcon avatar={preset.avatar} seed="another-surface" />);
  expect(paths()).toEqual(first);
});
