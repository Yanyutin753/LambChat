export type SendModifier = "ctrl" | "shift" | "enter";

/** Kept as newlineModifier for backend metadata compatibility. */
export const SEND_MODIFIER_STORAGE_KEY = "newlineModifier";
export const DEFAULT_SEND_MODIFIER: SendModifier = "ctrl";

type StorageReader = Pick<Storage, "getItem">;

export function parseSendModifier(
  stored: string | null | undefined,
): SendModifier {
  if (stored === "enter") return "enter";
  return stored === "shift" ? "shift" : "ctrl";
}

export function readSendModifier(
  storage: StorageReader = localStorage,
): SendModifier {
  return parseSendModifier(storage.getItem(SEND_MODIFIER_STORAGE_KEY));
}

export function isSendEnterKey(
  event: Pick<KeyboardEvent, "ctrlKey" | "metaKey" | "shiftKey">,
  modifier: SendModifier = readSendModifier(),
): boolean {
  if (modifier === "enter") {
    return !event.ctrlKey && !event.metaKey && !event.shiftKey;
  }
  return modifier === "ctrl" ? event.ctrlKey || event.metaKey : event.shiftKey;
}

export function getSendShortcutDisplay(modifier: SendModifier): {
  keys: string[];
  macKeys: string[];
} {
  if (modifier === "ctrl") {
    return {
      keys: ["Ctrl", "Enter"],
      macKeys: ["⌘", "Enter"],
    };
  }
  if (modifier === "enter") {
    return {
      keys: ["Enter"],
      macKeys: ["Enter"],
    };
  }
  return {
    keys: ["Shift", "Enter"],
    macKeys: ["Shift", "Enter"],
  };
}
