import {
  loadHistoryUntilMessageFound,
  type LoadUntilFoundControls,
} from "../bookmarkHistoryPaging";

function makeControls(overrides: Partial<LoadUntilFoundControls> = {}) {
  const state = { found: false, hasMore: true, pages: 0 };
  const controls: LoadUntilFoundControls = {
    isFound: () => state.found,
    hasMore: () => state.hasMore,
    loadOlder: async () => {
      state.pages += 1;
      // 第二页加载完成后目标出现
      if (state.pages >= 2) state.found = true;
    },
    sleep: async () => {},
    ...overrides,
  };
  return { controls, state };
}

test("resolves immediately when the message is already loaded", async () => {
  const { controls, state } = makeControls({ isFound: () => true });

  const result = await loadHistoryUntilMessageFound(controls);

  expect(result).toBe("found");
  expect(state.pages).toBe(0);
});

test("pages older history until the target message appears", async () => {
  const { controls, state } = makeControls();

  const result = await loadHistoryUntilMessageFound(controls);

  expect(result).toBe("found");
  expect(state.pages).toBe(2);
});

test("returns exhausted when there is nothing older left", async () => {
  let pages = 0;
  const { controls } = makeControls({
    loadOlder: async () => {
      pages += 1;
    },
    hasMore: () => pages < 1,
  });

  const result = await loadHistoryUntilMessageFound(controls);

  expect(result).toBe("exhausted");
  expect(pages).toBe(1);
});

test("stops at the page cap instead of looping forever", async () => {
  const { controls, state } = makeControls({
    loadOlder: async () => {
      state.pages += 1;
      // 永远找不到
    },
  });
  state.found = false;
  const neverFound = { ...controls, isFound: () => false };

  const result = await loadHistoryUntilMessageFound(neverFound, {
    maxPages: 3,
  });

  expect(result).toBe("exhausted");
  expect(state.pages).toBe(3);
});

test("waits for state to settle between pages", async () => {
  const sleeps: number[] = [];
  const { controls } = makeControls();

  await loadHistoryUntilMessageFound({
    ...controls,
    sleep: async (ms) => {
      sleeps.push(ms);
    },
  });

  expect(sleeps.length).toBe(2);
  expect(sleeps.every((ms) => ms > 0)).toBe(true);
});
