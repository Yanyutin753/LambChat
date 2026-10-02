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

test("a missing opener returns to the selected control in its surviving panel", () => {
  const panel = document.createElement("main");
  panel.innerHTML =
    '<button id="other">Other</button><button id="selected" aria-pressed="true">Selected</button><button id="opener">Open details</button>';
  document.body.append(panel);
  const opener = panel.querySelector<HTMLElement>("#opener")!;
  opener.focus();
  opener.hidden = true;
  opener.blur();

  restoreOpenerFocusUnclaimed(opener, null);
  expect(document.activeElement?.id).toBe("selected");
});

test("closing a dialog preserves focus that another page action already owns", () => {
  document.body.innerHTML =
    '<button id="opener">Open details</button><button id="next">Next task</button>';
  const opener = document.getElementById("opener")!;
  const next = document.getElementById("next")!;
  next.focus();

  restoreOpenerFocusUnclaimed(opener, null);
  expect(next).toHaveFocus();
});

test("a missing opener returns to the parent dialog without entering its inert descendants", () => {
  const opener = document.createElement("button");
  const parent = addDialog("parent");
  parent.tabIndex = -1;
  parent.innerHTML =
    '<div inert><button>Hidden action</button></div><button id="parent-action">Parent action</button>';

  restoreOpenerFocusUnclaimed(opener, null);
  expect(document.activeElement?.id).toBe("parent-action");
});

test("fallback focus includes a rich text editor without an explicit tab stop", () => {
  const parent = addDialog("parent");
  parent.tabIndex = -1;
  parent.innerHTML = '<div contenteditable="true" role="textbox">Draft</div>';

  restoreOpenerFocusUnclaimed(null, null);
  expect(parent.querySelector('[role="textbox"]')).toHaveFocus();
});

test("fallback skips a header without controls while the closing surface still has focus", () => {
  document.body.innerHTML =
    '<header><h1>Workspace</h1></header><main><button id="task">Continue task</button></main>';
  const closing = addDialog("closing");
  closing.tabIndex = -1;
  closing.focus();

  restoreOpenerFocusUnclaimed(null, closing);
  expect(document.getElementById("task")).toHaveFocus();
});
