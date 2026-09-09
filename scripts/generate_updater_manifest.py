"""生成桌面端自更新清单 latest.json（app-release 与手动 publish 工作流共用）。

用法：
  RELEASE_TAG=v2.9.3 ASSET_DIR=release-assets uv run python scripts/generate_updater_manifest.py

从 ASSET_DIR 下的各平台 .sig 文件组装清单（端点见 tauri.conf.json
updater.endpoints）；版本取自 tag（app-release 的 preflight 已校验与六处
版本文件一致）；macOS updater 走 .app.tar.gz，dmg 仅用于首装。
缺某平台 sig 时告警并省略该条目（发布完成的判据是五桌面齐全——由调用方
校验，本脚本只如实反映现状）。

下载 URL 走 lambchat.com 自托管反代并锁 ``?tag=``：国内直连 GitHub 下载
必挂；反代路由按 tag 查资产，发新版瞬间 latest 前移也不会 404。
"""

from __future__ import annotations

import datetime
import glob
import json
import os
import pathlib
import sys

PROXY_ASSET_BASE = "https://lambchat.com/api/version/assets"

MAPPING = [
    ("windows-x86_64", "*_x64_en-US.msi.sig", "Windows.msi"),
    ("linux-x86_64", "*_amd64.AppImage.sig", "Linux-x86_64.AppImage"),
    ("linux-aarch64", "*_aarch64.AppImage.sig", "Linux-arm64.AppImage"),
    # 双 darwin：sig 按 Tauri updater 产物名的 arch 段区分
    ("darwin-aarch64", "*-macOS-Apple-Silicon.app.tar.gz.sig", "macOS-Apple-Silicon.app.tar.gz"),
    ("darwin-x86_64", "*-macOS-Intel.app.tar.gz.sig", "macOS-Intel.app.tar.gz"),
]

REQUIRED_PLATFORMS = ("darwin-aarch64", "darwin-x86_64", "linux-x86_64", "windows-x86_64")


def main() -> int:
    tag = os.environ.get("RELEASE_TAG", "").strip()
    asset_dir = pathlib.Path(os.environ.get("ASSET_DIR", "release-assets"))
    if not tag.startswith("v"):
        print(f"RELEASE_TAG 必须形如 v2.9.3，收到: {tag!r}", file=sys.stderr)
        return 1

    version = tag.lstrip("v")

    def sig(pattern: str) -> str | None:
        files = sorted(glob.glob(str(asset_dir / pattern)))
        return pathlib.Path(files[0]).read_text().strip() if files else None

    platforms: dict[str, dict[str, str]] = {}
    for key, pattern, asset_suffix in MAPPING:
        signature = sig(pattern)
        if signature:
            asset_name = f"LambChat-{tag}-{asset_suffix}"
            platforms[key] = {
                "signature": signature,
                "url": f"{PROXY_ASSET_BASE}/{asset_name}/download?tag={tag}",
            }
        else:
            print(f"WARN: no sig file matches {pattern}, platform {key} omitted")

    manifest = {
        "version": version,
        "notes": f"LambChat {tag}",
        "pub_date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platforms": platforms,
    }
    out = asset_dir / "latest.json"
    out.write_text(json.dumps(manifest, indent=2))
    print(f"latest.json platforms: {sorted(platforms)}")

    if not all(p in platforms for p in REQUIRED_PLATFORMS):
        print(
            "发布判据未满足（五桌面须齐全，含 darwin-x86_64）——清单已生成但缺:",
            [p for p in REQUIRED_PLATFORMS if p not in platforms],
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
