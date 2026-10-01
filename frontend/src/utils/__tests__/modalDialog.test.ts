/** @vitest-environment jsdom */
import { afterEach, expect, test } from "vitest";
import {
  hasVisibleModalDialog,
  restoreOpenerFocusUnclaimed,
  topmostVisibleModalDialog,
} from "../modalDialog";

afterEach(() => {
  document.body.innerHTML = "";
});

function addDialog(
  id: string,
  modifiers: { hidden?: boolean; inert?: boolean; ariaHidden?: boolean } = {},
) {
  const el = document.createElement("div");
  el.id = id;
  el.setAttribute("role", "dialog");
  el.setAttribute("aria-modal", "true");
  if (modifiers.hidden) el.hidden = true;
  if (modifiers.inert) el.setAttribute("inert", "");
  if (modifiers.ariaHidden) el.setAttribute("aria-hidden", "true");
  document.body.append(el);
  return el;
}

test("topmostVisibleModalDialog ignores hidden tab panels that sit later in the DOM", () => {
  const active = addDialog("active-panel");
  addDialog("hidden-panel", { hidden: true });
  addDialog("inert-panel", { inert: true });
  addDialog("aria-hidden-panel", { ariaHidden: true });

  expect(topmostVisibleModalDialog()).toBe(active);
  expect(hasVisibleModalDialog()).toBe(true);
});

test("hasVisibleModalDialog is false when every modal panel is hidden", () => {
  addDialog("hidden-panel", { hidden: true });
  addDialog("inert-panel", { inert: true });

  expect(hasVisibleModalDialog()).toBe(false);
  expect(topmostVisibleModalDialog()).toBeNull();
});

test("restoreOpenerFocusUnclaimed returns focus when no overlay claimed it", () => {
  const opener = document.createElement("button");
  document.body.append(opener);
  document.body.focus();

  restoreOpenerFocusUnclaimed(opener, null);
  expect(document.activeElement).toBe(opener);
});

test("restoreOpenerFocusUnclaimed keeps focus inside a newer overlay that claimed it", () => {
  const opener = document.createElement("button");
  document.body.append(opener);
  const nextDialog = addDialog("next-dialog");
  nextDialog.innerHTML = '<button id="next-focus" type="button"></button>';
  (nextDialog.querySelector("#next-focus") as HTMLElement).focus();

  const closingSurface = document.createElement("div");
  restoreOpenerFocusUnclaimed(opener, closingSurface);
  expect(document.activeElement?.id).toBe("next-focus");
});

test("restoreOpenerFocusUnclaimed still restores when the active element is the closing overlay itself", () => {
  const opener = document.createElement("button");
  document.body.append(opener);
  const closing = addDialog("closing-dialog");
  closing.focus();

  restoreOpenerFocusUnclaimed(opener, closing);
  expect(document.activeElement).toBe(opener);
});
