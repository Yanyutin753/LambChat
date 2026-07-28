import {
  DEFAULT_SEND_MODIFIER,
  getSendShortcutDisplay,
  isSendEnterKey,
  parseSendModifier,
  SEND_MODIFIER_STORAGE_KEY,
  readSendModifier,
} from "../sendModifier";

test("parseSendModifier defaults empty/unknown values to ctrl", () => {
  expect(parseSendModifier(null)).toBe("ctrl");
  expect(parseSendModifier(undefined)).toBe("ctrl");
  expect(parseSendModifier("")).toBe("ctrl");
  expect(parseSendModifier("nope")).toBe("ctrl");
  expect(parseSendModifier("ctrl")).toBe("ctrl");
  expect(parseSendModifier("shift")).toBe("shift");
});

test("readSendModifier uses storage key and default", () => {
  const storage = {
    getItem: (key: string) =>
      key === SEND_MODIFIER_STORAGE_KEY ? null : "shift",
  };
  expect(readSendModifier(storage)).toBe(DEFAULT_SEND_MODIFIER);

  const stored = {
    getItem: (key: string) =>
      key === SEND_MODIFIER_STORAGE_KEY ? "shift" : null,
  };
  expect(readSendModifier(stored)).toBe("shift");
});

test("isSendEnterKey treats ctrl mode as ctrl or meta", () => {
  expect(
    isSendEnterKey({ ctrlKey: true, metaKey: false, shiftKey: false }, "ctrl"),
  ).toBe(true);
  expect(
    isSendEnterKey({ ctrlKey: false, metaKey: true, shiftKey: false }, "ctrl"),
  ).toBe(true);
  expect(
    isSendEnterKey({ ctrlKey: false, metaKey: false, shiftKey: true }, "ctrl"),
  ).toBe(false);
});

test("isSendEnterKey treats shift mode as shift only", () => {
  expect(
    isSendEnterKey({ ctrlKey: true, metaKey: false, shiftKey: false }, "shift"),
  ).toBe(false);
  expect(
    isSendEnterKey({ ctrlKey: false, metaKey: false, shiftKey: true }, "shift"),
  ).toBe(true);
});

test("getSendShortcutDisplay keeps dialog in sync with default ctrl mode", () => {
  expect(getSendShortcutDisplay("ctrl")).toEqual({
    keys: ["Ctrl", "Enter"],
    macKeys: ["⌘", "Enter"],
  });
  expect(getSendShortcutDisplay("shift")).toEqual({
    keys: ["Shift", "Enter"],
    macKeys: ["Shift", "Enter"],
  });
  expect(getSendShortcutDisplay(parseSendModifier(null))).toEqual({
    keys: ["Ctrl", "Enter"],
    macKeys: ["⌘", "Enter"],
  });
});
