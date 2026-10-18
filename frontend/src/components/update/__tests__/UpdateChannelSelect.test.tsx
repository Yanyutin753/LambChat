/** @vitest-environment jsdom */
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test } from "vitest";
import i18n from "../../../i18n";
import {
  getUpdateChannel,
  setUpdateBusy,
  setUpdateChannel,
} from "../../../utils/updateChannel";
import { UpdateChannelSelect } from "../UpdateChannelSelect";

beforeEach(async () => {
  setUpdateBusy(false);
  setUpdateChannel("stable");
  await i18n.changeLanguage("en");
});

afterEach(() => {
  cleanup();
  setUpdateBusy(false);
  setUpdateChannel("stable");
});

test("shows both channels and switches the selected channel with its warning", async () => {
  const user = userEvent.setup();
  render(<UpdateChannelSelect />);
  expect(screen.getByRole("radio", { name: /stable/i })).toBeChecked();
  const dev = screen.getByRole("radio", { name: i18n.t("update.channelDev") });
  await user.click(dev);
  expect(dev).toBeChecked();
  expect(getUpdateChannel()).toBe("dev");
  expect(screen.getByText(i18n.t("update.channelDevHint"))).toBeVisible();
  await user.click(screen.getByRole("radio", { name: /stable/i }));
  expect(screen.queryByText(i18n.t("update.channelDevHint"))).toBeNull();
});

test("supports keyboard selection and disables both channels during an update", async () => {
  const user = userEvent.setup();
  render(<UpdateChannelSelect />);
  await user.tab();
  expect(screen.getByRole("radio", { name: /stable/i })).toHaveFocus();
  await user.keyboard("{ArrowRight}");
  expect(
    screen.getByRole("radio", { name: i18n.t("update.channelDev") }),
  ).toBeChecked();
  act(() => setUpdateBusy(true));
  for (const radio of screen.getAllByRole("radio"))
    expect(radio).toBeDisabled();
  await user.click(screen.getByRole("radio", { name: /stable/i }));
  expect(getUpdateChannel()).toBe("dev");
});
