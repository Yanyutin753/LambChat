import {
  buildProxyCoverUrl,
  buildImageThumbUrl,
  buildVideoThumbChain,
      isOssDirectUrl,
    tokenizeCodeLine,
} from "../coverTheme.ts";

/* ── OSS direct URL detection ────────────────────────── */

test("isOssDirectUrl accepts aliyun virtual-hosted and path-style URLs", () => {
  expect(
    isOssDirectUrl("https://lambchat.oss-cn-hongkong.aliyuncs.com/a/b.png"),
  ).toBe(true);
  expect(
    isOssDirectUrl("https://oss-cn-hongkong.aliyuncs.com/lambchat/a.png"),
  ).toBe(true);
});

test("isOssDirectUrl rejects relative paths and non-OSS hosts", () => {
  expect(isOssDirectUrl("/api/files/x.png")).toBe(false);
  expect(isOssDirectUrl("https://cdn.example.com/x.png")).toBe(false);
  expect(isOssDirectUrl("http://localhost:9000/bucket/x.png")).toBe(false);
  expect(isOssDirectUrl("")).toBe(false);
});

/* ── Image thumbnail URL ─────────────────────────────── */

test("buildImageThumbUrl appends a 16:9 fill resize param on OSS URLs", () => {
  expect(
    buildImageThumbUrl("https://b.oss-cn-hongkong.aliyuncs.com/p/x.jpg"),
  ).toBe(
    "https://b.oss-cn-hongkong.aliyuncs.com/p/x.jpg?x-oss-process=image%2Fresize%2Cm_fill%2Cw_560%2Ch_315",
  );
});

test("buildImageThumbUrl keeps existing query params", () => {
  expect(
    buildImageThumbUrl("https://b.oss-cn-hongkong.aliyuncs.com/p/x.png?v=2"),
  ).toBe(
    "https://b.oss-cn-hongkong.aliyuncs.com/p/x.png?v=2&x-oss-process=image%2Fresize%2Cm_fill%2Cw_560%2Ch_315",
  );
});

test("buildImageThumbUrl returns null for gif/svg and non-OSS URLs", () => {
  expect(
    buildImageThumbUrl("https://b.oss-cn-hongkong.aliyuncs.com/p/cat.gif"),
  ).toBe(null);
  expect(
    buildImageThumbUrl("https://b.oss-cn-hongkong.aliyuncs.com/p/icon.svg"),
  ).toBe(null);
  expect(buildImageThumbUrl("/api/files/x.png")).toBe(null);
  expect(buildImageThumbUrl("")).toBe(null);
});

/* ── Video thumbnail chain ───────────────────────────── */

test("buildVideoThumbChain tries 1s first, then 0s, only on OSS URLs", () => {
  const chain = buildVideoThumbChain(
    "https://b.oss-cn-hongkong.aliyuncs.com/p/clip.mp4",
  );
  expect(chain).toHaveLength(2);
  expect(chain![0]).toContain("t_1000");
  expect(chain![0]).toContain("f_jpg");
  expect(chain![0]).toContain("m_fast");
  expect(chain![1]).toContain("t_0");
  expect(buildVideoThumbChain("/api/files/clip.mp4")).toBe(null);
});

/* ── Code line tinting ───────────────────────────────── */

test("tokenizeCodeLine marks full-line comments as muted", () => {
  const tokens = tokenizeCodeLine("// build the thing");
  expect(tokens).toHaveLength(1);
  expect(tokens[0].tone).toBe("muted");
  expect(tokenizeCodeLine("# python note")[0].tone).toBe("muted");
});

test("tokenizeCodeLine accents quoted strings and literals for numbers", () => {
  const tokens = tokenizeCodeLine(`const name = "lamb";`);
  const joined = tokens.map((t) => t.text).join("");
  expect(joined).toBe(`const name = "lamb";`);
  const str = tokens.find((t) => t.text.includes("lamb"));
  expect(str?.tone).toBe("accent");
  const num = tokenizeCodeLine("return 42;");
  expect(num.find((t) => t.text.includes("42"))?.tone).toBe("literal");
});

/* ── App proxy cover URLs ────────────────────────────── */

test("buildProxyCoverUrl appends ?cover=1 to app proxy file URLs", () => {
  expect(
    buildProxyCoverUrl("https://lambchat.com/api/upload/file/revealed_files/a.jpg"),
  ).toBe("https://lambchat.com/api/upload/file/revealed_files/a.jpg?cover=1");
  expect(buildProxyCoverUrl("/api/upload/file/a.jpg")).toBe(
    "/api/upload/file/a.jpg?cover=1",
  );
});

test("buildProxyCoverUrl carries video timestamps and existing params", () => {
  expect(
    buildProxyCoverUrl("/api/upload/file/a/clip.mp4", { t: 1000 }),
  ).toBe("/api/upload/file/a/clip.mp4?cover=1&t=1000");
  expect(
    buildProxyCoverUrl("/api/upload/file/a.mp4?x=2", { t: 0 }),
  ).toBe("/api/upload/file/a.mp4?x=2&cover=1&t=0");
});

test("buildProxyCoverUrl returns null for non-proxy URLs", () => {
  expect(
    buildProxyCoverUrl("https://b.oss-cn-hongkong.aliyuncs.com/p/a.jpg"),
  ).toBe(null);
  expect(buildProxyCoverUrl("/api/other")).toBe(null);
  expect(buildProxyCoverUrl("")).toBe(null);
});
