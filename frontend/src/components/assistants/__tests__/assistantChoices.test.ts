import { expect, test, vi } from "vitest";
import { loadAssistantChoices } from "../assistantChoices";

test("resource choices include later pages without chasing concurrent insertions", async () => {
  const load = vi
    .fn()
    .mockResolvedValueOnce({
      items: [{ id: "first", name: "First" }],
      total: 2,
    })
    .mockResolvedValueOnce({
      items: [{ id: "later", name: "Later" }],
      total: 50,
    });
  const result = await loadAssistantChoices(load, () => true);
  expect(result.map((item) => item.value)).toEqual(["first", "later"]);
  expect(load.mock.calls).toEqual([[0], [1]]);
});

test("an incomplete page is a visible load failure, not an apparently complete picker", async () => {
  const load = vi
    .fn()
    .mockResolvedValueOnce({
      items: [{ id: "first", name: "First" }],
      total: 2,
    })
    .mockResolvedValueOnce({ items: [], total: 2 });
  await expect(loadAssistantChoices(load, () => true)).rejects.toThrow();
});
