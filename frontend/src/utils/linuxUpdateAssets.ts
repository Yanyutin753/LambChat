/**
 * Linux deb/rpm 更新链路的纯函数。
 *
 * 资产名与 .github/workflows/app-release.yml 的收集命名一一对应
 * （`LambChat-${RELEASE_TAG}-Linux-${arch}.deb|.rpm`，arch 取值 x86_64 | arm64），
 * 改任一侧都要同步另一侧（scripts/e2e_linux_update.py 固化该契约）。
 */

import { buildReleaseAssetDownloadUrl } from "../services/api/version";

/** 规范化 release tag：updater 上报的版本无 v 前缀，tag 一律有。 */
export function normalizeVersionTag(version: string): string {
  return version.startsWith("v") ? version : `v${version}`;
}

/** 拼装 deb/rpm 安装包资产名（arch 来自 Rust 侧 get_linux_install_source 上报）。 */
export function buildLinuxPackageAssetName(
  version: string,
  arch: string,
  kind: "deb" | "rpm",
): string {
  return `LambChat-${normalizeVersionTag(version)}-Linux-${arch}.${kind}`;
}

/**
 * deb/rpm 安装包的同源反代下载 URL。
 *
 * `?tag=` 锁定版本所属 release：发新版瞬间 latest 前移时，老资产名仍能在
 * 其所属 release 中找到（与自更新清单同款防竞态语义）。
 */
export function buildLinuxPackageDownloadUrl(
  assetName: string,
  version: string,
  apiBase?: string,
): string {
  const base =
    apiBase === undefined
      ? buildReleaseAssetDownloadUrl(assetName)
      : buildReleaseAssetDownloadUrl(assetName, apiBase);
  return `${base}?tag=${encodeURIComponent(normalizeVersionTag(version))}`;
}
