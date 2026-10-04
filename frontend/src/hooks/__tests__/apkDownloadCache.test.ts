/** Android 更新包缓存判定：已完整下载的 APK 直接安装，绝不重复下载。 */

import { isDownloadedApkComplete } from "../useAutoUpdate";

const ok = { exists: true, size: 86_234_112, path: "/data/update.apk" };

test("complete file with matching size is reusable", () => {
  expect(isDownloadedApkComplete(ok, 86_234_112)).toBe(true);
});

test("size mismatch means partial/stale file and must re-download", () => {
  expect(isDownloadedApkComplete(ok, 1_000)).toBe(false);
  // 零字节文件不可能是完整安装包
  expect(isDownloadedApkComplete({ ...ok, size: 0 }, 0)).toBe(false);
});

test("missing expected size falls back to trusting a non-empty file", () => {
  // /api/version 未带回 size（老 release 元数据）时按「存在且非空」判定
  expect(isDownloadedApkComplete(ok, undefined)).toBe(true);
  expect(isDownloadedApkComplete({ ...ok, size: 0 }, undefined)).toBe(false);
});

test("missing file is never reusable", () => {
  expect(
    isDownloadedApkComplete({ exists: false, size: 0 }, 86_234_112),
  ).toBe(false);
});
