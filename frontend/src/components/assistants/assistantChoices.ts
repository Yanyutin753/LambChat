import type { SelectOption } from "../common/ui";

export async function loadAssistantChoices(
  load: (
    skip: number,
  ) => Promise<{ items: Array<{ id: string; name: string }>; total: number }>,
  active: () => boolean,
): Promise<SelectOption[]> {
  const first = await load(0);
  const items = [...first.items];
  // Freeze the initial count so concurrent additions cannot extend this load forever.
  const total = first.total;
  while (active() && items.length < total) {
    const next = await load(items.length);
    if (!next.items.length) throw new Error("Resource page is incomplete");
    items.push(...next.items);
  }
  return [
    ...new Map(
      items.map((item) => [item.id, { value: item.id, label: item.name }]),
    ).values(),
  ];
}
