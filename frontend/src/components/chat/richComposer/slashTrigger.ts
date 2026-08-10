export interface SlashTrigger {
  from: number;
  to: number;
  query: string;
}

export function getSlashTokenId(
  nodeKey: string,
  text: string,
  from: number,
): string {
  const slashWord = /^\/[^/\s]*/.exec(text.slice(from))?.[0] ?? "";
  return `${nodeKey}:${from}:${slashWord}`;
}

export function findSlashTrigger(
  text: string,
  caretOffset: number,
): SlashTrigger | null {
  if (caretOffset < 0 || caretOffset > text.length) return null;

  const textBeforeCaret = text.slice(0, caretOffset);
  const match = /(?:^|\s)\/([^/\s]*)$/.exec(textBeforeCaret);
  if (!match) return null;

  const from = textBeforeCaret.lastIndexOf("/");
  return {
    from,
    to: caretOffset,
    query: textBeforeCaret.slice(from + 1),
  };
}
