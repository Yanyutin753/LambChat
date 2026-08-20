export function getUserMessageActionButtonVisibilityClass(
  _isLastMessage?: boolean,
) {
  // Actions remain discoverable on every message. Hover-only controls made
  // earlier messages look as if they had no actions, especially in desktop
  // sessions where users do not know which row to hover.
  return "";
}
