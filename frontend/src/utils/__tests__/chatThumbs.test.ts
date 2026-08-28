import { describe, expect, test } from "vitest";
import {
  buildChatThumbUrl,
  buildFileCoverUrl,
  isChatCoverableFile,
} from "../chatThumbs";

describe("buildChatThumbUrl", () => {
  test("appends thumb=1 to app proxy upload URLs", () => {
    expect(
      buildChatThumbUrl("http://127.0.0.1:8000/api/upload/file/abc/hero.jpg"),
    ).toBe("http://127.0.0.1:8000/api/upload/file/abc/hero.jpg?thumb=1");
  });

  test("supports relative upload URLs and existing query strings", () => {
    expect(buildChatThumbUrl("/api/upload/file/abc/hero.png")).toBe(
      "/api/upload/file/abc/hero.png?thumb=1",
    );
    expect(buildChatThumbUrl("/api/upload/file/abc/hero.jpg?proxy=true")).toBe(
      "/api/upload/file/abc/hero.jpg?proxy=true&thumb=1",
    );
  });

  test("appends x-oss-process lfit to Aliyun direct URLs", () => {
    expect(
      buildChatThumbUrl(
        "https://bucket.oss-cn-hangzhou.aliyuncs.com/path/hero.jpg",
      ),
    ).toBe(
      "https://bucket.oss-cn-hangzhou.aliyuncs.com/path/hero.jpg" +
        "?x-oss-process=image%2Fresize%2Cm_lfit%2Cw_560%2Ch_560",
    );
  });

  test("returns undefined for formats that must keep the original", () => {
    expect(buildChatThumbUrl("/api/upload/file/abc/anim.gif")).toBeUndefined();
    expect(buildChatThumbUrl("/api/upload/file/abc/icon.svg")).toBeUndefined();
    expect(buildChatThumbUrl("/api/upload/file/abc/anim.apng")).toBeUndefined();
  });

  test("returns undefined for external and non-upload URLs", () => {
    expect(
      buildChatThumbUrl("https://example.com/random/photo.jpg"),
    ).toBeUndefined();
    expect(buildChatThumbUrl("data:image/png;base64,xxx")).toBeUndefined();
    expect(buildChatThumbUrl(undefined)).toBeUndefined();
    expect(buildChatThumbUrl("")).toBeUndefined();
  });
});

describe("buildFileCoverUrl", () => {
  test("appends cover=1 to app proxy upload URLs", () => {
    expect(buildFileCoverUrl("/api/upload/file/abc/report.pdf")).toBe(
      "/api/upload/file/abc/report.pdf?cover=1",
    );
    expect(buildFileCoverUrl("/api/upload/file/abc/report.pdf", { t: 0 })).toBe(
      "/api/upload/file/abc/report.pdf?cover=1&t=0",
    );
  });

  test("returns undefined for non upload URLs", () => {
    expect(
      buildFileCoverUrl("https://example.com/random/report.pdf"),
    ).toBeUndefined();
    expect(buildFileCoverUrl(undefined)).toBeUndefined();
  });
});

describe("isChatCoverableFile", () => {
  test("covers documents and videos, not plain code/text", () => {
    expect(isChatCoverableFile("pdf")).toBe(true);
    expect(isChatCoverableFile("xlsx")).toBe(true);
    expect(isChatCoverableFile("mp4")).toBe(true);
    expect(isChatCoverableFile("webm")).toBe(true);
    expect(isChatCoverableFile("txt")).toBe(false);
    expect(isChatCoverableFile("zip")).toBe(false);
  });
});
