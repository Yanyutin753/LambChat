/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { TeamMemberCard } from "../TeamMemberCard";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../i18n", () => ({ default: { language: "en" } }));
afterEach(cleanup);

function renderMember(instructions = "") {
  const onRemove = vi.fn();
  const onSetDefault = vi.fn();
  render(
    <TeamMemberCard
      member={{
        member_id: "member-1",
        persona_preset_id: "persona-1",
        role_name: "Researcher",
        role_tags: [],
        role_instructions: instructions,
        position: 0,
        enabled: true,
      }}
      isDefault={false}
      onRemove={onRemove}
      onSetDefault={onSetDefault}
      onToggleEnabled={vi.fn()}
      onInstructionsChange={vi.fn()}
      onModelChange={vi.fn()}
    />,
  );
  return { onRemove, onSetDefault };
}

test("member actions have distinct names and retain their callbacks", () => {
  const { onRemove, onSetDefault } = renderMember();
  fireEvent.click(
    screen.getByRole("button", { name: "team.setDefault Researcher" }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "team.remove Researcher" }),
  );
  expect(onSetDefault).toHaveBeenCalledOnce();
  expect(onRemove).toHaveBeenCalledOnce();
});

test("collapsed member settings are inert until their named disclosure opens", () => {
  renderMember();
  const disclosure = screen.getByRole("button", {
    name: "common.expand Researcher",
  });
  const instructions = screen.getByLabelText(
    "team.roleInstructions Researcher",
  );
  expect(disclosure.getAttribute("aria-expanded")).toBe("false");
  expect(instructions.closest("[inert]")).not.toBeNull();
  fireEvent.click(disclosure);
  expect(
    screen
      .getByRole("button", { name: "common.collapse Researcher" })
      .getAttribute("aria-expanded"),
  ).toBe("true");
  expect(instructions.closest("[inert]")).toBeNull();
  expect(
    screen.getByRole("textbox", { name: "team.roleInstructions Researcher" }),
  ).toBe(instructions);
});

test("configured members start as summaries and retain instructions when opened", () => {
  renderMember("Preserve this guidance");
  const disclosure = screen.getByRole("button", {
    name: "common.expand Researcher",
  });
  expect(disclosure).toHaveAttribute("aria-expanded", "false");
  const controls = disclosure.getAttribute("aria-controls");
  expect(controls).toBeTruthy();
  expect(document.getElementById(controls!)).toHaveAttribute("inert");
  fireEvent.click(disclosure);
  expect(
    screen.getByRole("textbox", { name: "team.roleInstructions Researcher" }),
  ).toHaveValue("Preserve this guidance");
});

test("Escape collapses just this member and returns focus without closing the editor", () => {
  const parentEscape = vi.fn();
  const { container } = render(
    <div onKeyDown={parentEscape}>
      <TeamMemberCard
        member={{
          member_id: "member-1",
          persona_preset_id: "persona-1",
          role_name: "Researcher",
          role_tags: [],
          role_instructions: "",
          position: 0,
          enabled: true,
        }}
        isDefault={false}
        onRemove={vi.fn()}
        onSetDefault={vi.fn()}
        onToggleEnabled={vi.fn()}
        onInstructionsChange={vi.fn()}
      />
    </div>,
  );
  const disclosure = screen.getByRole("button", {
    name: "common.expand Researcher",
  });
  fireEvent.click(disclosure);
  const instructions = screen.getByRole("textbox", {
    name: "team.roleInstructions Researcher",
  });
  fireEvent.keyDown(instructions, { key: "Escape", isComposing: true });
  expect(disclosure).toHaveAttribute("aria-expanded", "true");
  fireEvent.keyDown(instructions, { key: "Escape" });
  expect(disclosure).toHaveAttribute("aria-expanded", "false");
  expect(disclosure).toHaveFocus();
  expect(parentEscape).not.toHaveBeenCalled();
  expect(container.querySelector("[inert]")).toBeTruthy();
});

test("collapsing a member also dismisses its portalled model choices", () => {
  renderMember("Keep guidance");
  const disclosure = screen.getByRole("button", {
    name: "common.expand Researcher",
  });
  fireEvent.click(disclosure);
  fireEvent.click(
    screen.getByRole("button", { name: "team.memberModel Researcher" }),
  );
  expect(screen.getByRole("listbox")).toBeTruthy();
  disclosure.focus();
  fireEvent.click(disclosure);
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(disclosure).toHaveFocus();
});
