/** @vitest-environment jsdom */
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeAll, expect, test } from "vitest";

import { PersonaPresetSelector } from "../PersonaPresetSelector";
import type { PersonaPreset } from "../../../../types";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
});

afterEach(() => {
  cleanup();
});

function preset(id: string): PersonaPreset {
  return {
    id,
    name: `Preset ${id}`,
    description: "",
    system_prompt: "",
    tags: [],
    scope: "global",
    avatar: "",
    usage_count: 0,
    is_favorite: false,
    is_pinned: false,
  } as PersonaPreset;
}

function renderSelector(props: { total: number; pageSize?: number }) {
  const presets = Array.from({ length: Math.min(props.total, 12) }, (_, i) =>
    preset(`p${i}`),
  );
  return render(
    <PersonaPresetSelector
      presets={presets}
      total={props.total}
      pageSize={props.pageSize}
      isOpen
      onOpenChange={() => undefined}
      onPageChange={() => undefined}
      onSearchChange={() => undefined}
      onTagChange={() => undefined}
      onUsePreset={async () => null}
      onCopyPreset={async () => undefined}
      onClearPreset={() => undefined}
    />,
  );
}

function pageNumbers(): string[] {
  return Array.from(
    document.body.querySelectorAll(".pagination-page"),
  ).map((el) => el.textContent ?? "");
}

test("pagination honors pageSize prop so remote pages match the fetched limit", () => {
  renderSelector({ total: 30, pageSize: 12 });
  expect(pageNumbers()).toContain("3");
});

test("pagination defaults to 20 per page when pageSize is omitted", () => {
  renderSelector({ total: 45 });
  expect(pageNumbers()).toContain("3");
});
