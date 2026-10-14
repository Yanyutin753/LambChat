/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import { AvatarSection } from "../PersonaEditorAvatarSection";

afterEach(cleanup);

test("the role and team editor's shared chooser saves a stable color avatar", async () => {
  const user = userEvent.setup();
  const change = vi.fn();
  render(<AvatarSection avatar="" onAvatarChange={change} onUploadingChange={vi.fn()} />);
  const trigger = screen.getByRole("button", { name: i18n.t("personaPresets.pickIcon") });
  await user.click(trigger);
  await user.click(screen.getByRole("button", { name: i18n.t("personaPresets.generatedAvatar", { number: 2 }) }));
  expect(change).toHaveBeenCalledWith("generated:avatar-2");
  expect(trigger).toHaveFocus();
  expect(screen.queryByRole("group", { name: i18n.t("personaPresets.pickIcon") })).toBeNull();
});
