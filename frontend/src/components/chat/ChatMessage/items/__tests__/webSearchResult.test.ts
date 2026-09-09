import { hostFromUrl, parseWebSearchResult, siteLabelFromUrl } from "../webSearchResult";

const payload = {
  success: true,
  query: "hello",
  provider: "tavily",
  results: [
    {
      title: "R1",
      url: "https://a.com/1",
      snippet: "snippet-1",
      score: 0.87,
      favicon_url: "https://a.com/f.ico",
      published_date: "2026-09-01",
    },
  ],
  images: [{ url: "https://img/1", description: "d1" }],
  answer: "42",
};

test("parses object result with snake_case fields", () => {
  const summary = parseWebSearchResult(payload);

  expect(summary).not.toBeNull();
  expect(summary!.provider).toBe("tavily");
  expect(summary!.answer).toBe("42");
  expect(summary!.results).toHaveLength(1);
  expect(summary!.results[0]).toEqual({
    title: "R1",
    url: "https://a.com/1",
    snippet: "snippet-1",
    score: 0.87,
    faviconUrl: "https://a.com/f.ico",
    publishedDate: "2026-09-01",
  });
  expect(summary!.images).toEqual([{ url: "https://img/1", description: "d1" }]);
});

test("parses JSON string result", () => {
  const summary = parseWebSearchResult(JSON.stringify(payload));

  expect(summary!.provider).toBe("tavily");
});

test("tolerates missing optional fields", () => {
  const summary = parseWebSearchResult({
    success: true,
    provider: "brave",
    results: [{ title: "B", url: "https://b.com/1", snippet: "" }],
    images: [],
  });

  expect(summary!.answer).toBeNull();
  expect(summary!.results[0].score).toBeNull();
  expect(summary!.results[0].faviconUrl).toBeNull();
  expect(summary!.results[0].publishedDate).toBeNull();
});

test("drops entries without url", () => {
  const summary = parseWebSearchResult({
    success: true,
    provider: "searxng",
    results: [
      { title: "ok", url: "https://s.com/1", snippet: "c" },
      { title: "bad", snippet: "no url" },
      "garbage",
    ],
    images: ["https://img/str", { description: "no url" }, 42],
  });

  expect(summary!.results).toHaveLength(1);
  expect(summary!.images).toEqual([{ url: "https://img/str", description: null }]);
});

test("returns null for failed or unparseable results", () => {
  expect(parseWebSearchResult({ success: false, error: "boom" })).toBeNull();
  expect(parseWebSearchResult("not json")).toBeNull();
  expect(parseWebSearchResult(undefined)).toBeNull();
  expect(parseWebSearchResult(42)).toBeNull();
});

test("siteLabelFromUrl strips subdomains like ChatGPT source cards", () => {
  expect(siteLabelFromUrl("https://zhuanlan.zhihu.com/p/1")).toBe("zhihu.com");
  expect(siteLabelFromUrl("https://www.53ai.com/news/x")).toBe("53ai.com");
  expect(siteLabelFromUrl("https://github.com/a/b")).toBe("github.com");
  expect(siteLabelFromUrl("https://open.bigmodel.cn/dev")).toBe("bigmodel.cn");
  expect(siteLabelFromUrl("https://www.bbc.co.uk/news")).toBe("bbc.co.uk");
  expect(siteLabelFromUrl("https://arxiv.org/abs/1")).toBe("arxiv.org");
  expect(siteLabelFromUrl("not a url")).toBe("");
});

test("hostFromUrl returns the full host", () => {
  expect(hostFromUrl("https://zhuanlan.zhihu.com/p/1")).toBe("zhuanlan.zhihu.com");
  expect(hostFromUrl("bad")).toBe("");
});
