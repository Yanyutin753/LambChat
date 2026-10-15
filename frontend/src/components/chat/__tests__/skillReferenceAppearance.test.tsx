/** @vitest-environment jsdom */
import { render } from "@testing-library/react";
import { createRef } from "react";
import { expect, test } from "vitest";
import { SkillChip } from "../SkillChip";
import { SlashDropdownMenu } from "../SlashDropdownMenu";
import {
  getSlashDropdownSections,
  type SlashDropdownItem,
} from "../chatInputSlashCommands";

test("skill references and slash choices use the skill card avatar", () => {
  const items: SlashDropdownItem[] = [
    {
      type: "skill",
      skill: { name: "writer", description: "", tags: ["writing"] },
    },
  ];
  const view = render(
    <>
      <SkillChip name="writer" />
      <SlashDropdownMenu
        open
        sections={getSlashDropdownSections(items)}
        items={items}
        runSkillNameSet={new Set()}
        containerRef={createRef()}
        onApplySelection={() => {}}
        highlightIndex={0}
        onHighlightChange={() => {}}
      />
    </>,
  );
  expect(
    view.container.querySelector('[data-avatar-style="boring"]'),
  ).not.toBeNull();
  const menu = document.querySelector('[role="listbox"]')!;
  expect(menu.querySelector('[data-avatar-style="boring"]')).not.toBeNull();
  expect(menu.classList.contains("font-serif")).toBe(true);
});
