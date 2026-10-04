/** Linux deb/rpm 更新链路的纯函数：资产名拼装与反代下载 URL（契约锁定 app-release.yml 命名）。 */

import {
  buildLinuxPackageAssetName,
  buildLinuxPackageDownloadUrl,
  findLinuxPackageAsset,
  normalizeVersionTag,
} from "../linuxUpdateAssets";

function asset(name: string, size = 86_234_112) {
  return {
    name,
    url: `https://github.com/Yanyutin753/LambChat/releases/download/v2.10.2/${name}`,
    size,
    content_type: "application/octet-stream",
  };
}

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

test("findLinuxPackageAsset picks the exact asset for version+arch+kind", () => {
  const assets = [
    asset("LambChat-v2.10.2-Linux-x86_64.rpm"),
    asset("LambChat-v2.10.2-Linux-x86_64.deb"),
    asset("LambChat-v2.10.2-Linux-arm64.deb"),
    asset("LambChat-v2.10.1-Linux-x86_64.deb"),
    asset("LambChat-android-v2.10.2-signed.apk"),
  ];
  // 版本无 v 前缀（/api/version latest_version 口径）也能命中
  expect(findLinuxPackageAsset(assets, "2.10.2", "x86_64", "deb")?.name).toBe(
    "LambChat-v2.10.2-Linux-x86_64.deb",
  );
  expect(findLinuxPackageAsset(assets, "v2.10.2", "arm64", "deb")?.name).toBe(
    "LambChat-v2.10.2-Linux-arm64.deb",
  );
});

test("findLinuxPackageAsset returns null when the target asset is missing", () => {
  const assets = [asset("LambChat-v2.10.2-Linux-x86_64.deb")];
  // 该 arch/kind 未发布（如 arm64 rpm 缺失）
  expect(findLinuxPackageAsset(assets, "2.10.2", "arm64", "rpm")).toBeNull();
  // 版本不匹配（旧版本资产不算数）
  expect(findLinuxPackageAsset(assets, "2.10.3", "x86_64", "deb")).toBeNull();
  expect(findLinuxPackageAsset([], "2.10.2", "x86_64", "deb")).toBeNull();
});
