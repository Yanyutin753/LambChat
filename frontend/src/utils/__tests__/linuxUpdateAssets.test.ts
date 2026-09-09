/** Linux deb/rpm 更新链路的纯函数：资产名拼装与反代下载 URL（契约锁定 app-release.yml 命名）。 */

import {
  buildLinuxPackageAssetName,
  buildLinuxPackageDownloadUrl,
  normalizeVersionTag,
} from "../linuxUpdateAssets";

test("asset name follows the release workflow naming (LambChat-v<tag>-Linux-<arch>.<ext>)", () => {
  expect(buildLinuxPackageAssetName("2.10.2", "x86_64", "deb")).toBe(
    "LambChat-v2.10.2-Linux-x86_64.deb",
  );
  expect(buildLinuxPackageAssetName("2.10.2", "arm64", "rpm")).toBe(
    "LambChat-v2.10.2-Linux-arm64.rpm",
  );
  // 已带 v 前缀的版本不重复加
  expect(buildLinuxPackageAssetName("v2.10.2", "x86_64", "deb")).toBe(
    "LambChat-v2.10.2-Linux-x86_64.deb",
  );
});

test("download url proxies through the backend and locks the release tag", () => {
  expect(
    buildLinuxPackageDownloadUrl(
      "LambChat-v2.10.2-Linux-x86_64.deb",
      "2.10.2",
      "http://127.0.0.1:8000",
    ),
  ).toBe(
    "http://127.0.0.1:8000/api/version/assets/LambChat-v2.10.2-Linux-x86_64.deb/download?tag=v2.10.2",
  );
  // 版本带 v 前缀时 tag 不重复加
  expect(
    buildLinuxPackageDownloadUrl(
      "LambChat-v2.10.2-Linux-arm64.rpm",
      "v2.10.2",
      "https://lambchat.com",
    ),
  ).toBe(
    "https://lambchat.com/api/version/assets/LambChat-v2.10.2-Linux-arm64.rpm/download?tag=v2.10.2",
  );
});

test("normalizeVersionTag is idempotent", () => {
  expect(normalizeVersionTag("2.10.2")).toBe("v2.10.2");
  expect(normalizeVersionTag("v2.10.2")).toBe("v2.10.2");
});
