/** 打包壳（Tauri/Capacitor）内文件预览 URL 解析。

 * webview origin（tauri://localhost、http://tauri.localhost、capacitor://localhost、
 * Android https://localhost）不是真实服务器：相对 URL 必须以运行时配置的
 * 服务器地址解析，否则 <img>/<video>/<audio> 等不经 fetch 改写的媒体元素
 * 全部 404——客户端"文件预览不了"的根因。 */
/** @vitest-environment jsdom */

import { beforeEach, expect, test } from "vitest";

import {
  buildUploadProxyUrl,
  buildUploadProxyUrlFromKey,
  getFullUrl,
} from "../config.ts";
import { clearStoredServerUrl, setStoredServerUrl } from "../serverConfig";

const nativeGlobal = { __TAURI__: {} } as const;

beforeEach(() => {
  window.localStorage.clear();
});

test("getFullUrl 以运行时服务器地址解析相对上传 URL（原生壳）", () => {
  setStoredServerUrl("https://lc.example.com");
  expect(
    getFullUrl("/api/upload/file/revealed_files/a/b.png", "", {
      globalLike: nativeGlobal,
    }),
  ).toBe("https://lc.example.com/api/upload/file/revealed_files/a/b.png");
});

test("getFullUrl 把指向 webview 自身 origin 的 http 地址重定向到真实服务器（原生壳）", () => {
  setStoredServerUrl("https://lc.example.com");
  // Android Capacitor（androidScheme=https）下 webview origin 即 https://localhost；
  // 这里用 jsdom 自身 origin 等价模拟"绝对地址 == webview origin"
  const webviewOriginUrl = `${window.location.origin}/api/upload/file/x.png`;
  expect(getFullUrl(webviewOriginUrl, "", { globalLike: nativeGlobal })).toBe(
    "https://lc.example.com/api/upload/file/x.png",
  );
});

test("getFullUrl 把 webview scheme 地址（tauri://localhost/...）重写为真实服务器（原生壳）", () => {
  setStoredServerUrl("https://lc.example.com");
  expect(
    getFullUrl("tauri://localhost/api/upload/file/x.png", "", {
      globalLike: nativeGlobal,
    }),
  ).toBe("https://lc.example.com/api/upload/file/x.png");
});

test("getFullUrl 不动外部绝对地址（原生壳）", () => {
  setStoredServerUrl("https://lc.example.com");
  expect(
    getFullUrl("https://cdn.example.com/img.png", "", {
      globalLike: nativeGlobal,
    }),
  ).toBe("https://cdn.example.com/img.png");
});

test("getFullUrl 原生壳未配置服务器时维持旧拼接行为", () => {
  clearStoredServerUrl();
  expect(
    getFullUrl("/api/upload/file/x.png", "", { globalLike: nativeGlobal }),
  ).toBe(`${window.location.origin}/api/upload/file/x.png`);
});

test("getFullUrl 透传 blob: 与 data: URL", () => {
  setStoredServerUrl("https://lc.example.com");
  expect(
    getFullUrl("data:image/png;base64,AAAA", "", { globalLike: nativeGlobal }),
  ).toBe("data:image/png;base64,AAAA");
  expect(
    getFullUrl("blob:http://localhost:3000/abc", "", {
      globalLike: nativeGlobal,
    }),
  ).toBe("blob:http://localhost:3000/abc");
});

test("getFullUrl Web 端相对 URL 仍按同源拼接（回归保护）", () => {
  expect(getFullUrl("/api/upload/file/x.png")).toBe(
    `${window.location.origin}/api/upload/file/x.png`,
  );
});

test("buildUploadProxyUrlFromKey 原生壳默认产出真实服务器的绝对地址", () => {
  setStoredServerUrl("https://lc.example.com");
  expect(
    buildUploadProxyUrlFromKey("revealed files/report 1.pdf", "", {
      globalLike: nativeGlobal,
    }),
  ).toBe(
    "https://lc.example.com/api/upload/file/revealed%20files/report%201.pdf",
  );
});

test("buildUploadProxyUrlFromKey Web 端默认仍返回相对路径（回归保护）", () => {
  expect(buildUploadProxyUrlFromKey("a/b.pdf", "")).toBe(
    "/api/upload/file/a/b.pdf",
  );
});

test("buildUploadProxyUrl 原生壳在真实服务器地址上追加 proxy=true", () => {
  setStoredServerUrl("https://lc.example.com");
  expect(
    buildUploadProxyUrl("/api/upload/file/a/report.pdf", "", {
      globalLike: nativeGlobal,
    }),
  ).toBe("https://lc.example.com/api/upload/file/a/report.pdf?proxy=true");
});
