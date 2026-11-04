/** A compact label only; the full request remains in task details. */
export function assistantTaskTitle(description: string): string {
  const firstLine = description.trim().split(/\r?\n/, 1)[0];
  return (
    firstLine.match(/^【([^】]+)】/u)?.[1] ??
    firstLine.split(/(?<=[。！？.!?])\s+/u, 1)[0]
  );
}
