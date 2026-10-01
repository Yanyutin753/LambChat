/** @vitest-environment jsdom */
import { useState } from "react";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { ModalSurface } from "../../common/ModalSurface";
import { AgentIconSelect } from "../AgentIconSelect";

afterEach(cleanup);

function Editor({ change }: { change: (value: string) => void }) {
  const [open, setOpen] = useState(true);
  return (
    <ModalSurface open={open} onClose={() => setOpen(false)} label="Editor">
      <AgentIconSelect value="Bot" onChange={change} />
    </ModalSurface>
  );
}

test("icon chooser owns Escape and returns focus to its trigger without closing the editor", async () => {
  const user = userEvent.setup();
  render(<Editor change={vi.fn()} />);
  const trigger = screen.getByRole("button", {
    name: i18n.t("personaPresets.pickIcon"),
  });
  await user.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  const picker = screen.getByRole("dialog", {
    name: i18n.t("personaPresets.pickIcon"),
  });
  expect(Number(picker.parentElement?.style.zIndex)).toBeGreaterThan(1000);
  expect(
    within(picker).getByRole("button", {
      name: i18n.t("personaPresets.emojiRobot"),
    }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(
    within(picker).getByRole("button", {
      name: i18n.t("personaPresets.emojiRobot"),
    }),
  ).toHaveClass("ui-button--secondary");
  await user.keyboard("{Escape}");
  expect(
    screen.queryByRole("dialog", { name: i18n.t("personaPresets.pickIcon") }),
  ).toBeNull();
  expect(screen.getByRole("dialog", { name: "Editor" })).toBeInTheDocument();
  await waitFor(() => expect(trigger).toHaveFocus());
});

test("keyboard selection reports the icon and returns to the editor", async () => {
  const user = userEvent.setup();
  const change = vi.fn();
  render(<Editor change={change} />);
  const trigger = screen.getByRole("button", {
    name: i18n.t("personaPresets.pickIcon"),
  });
  await user.click(trigger);
  screen
    .getByRole("button", { name: i18n.t("personaPresets.emojiAcademic") })
    .focus();
  await user.keyboard("{Enter}");
  expect(change).toHaveBeenCalledWith("🎓");
  await waitFor(() => expect(trigger).toHaveFocus());
});
