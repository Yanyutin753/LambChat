#!/usr/bin/env python3
"""桌面端 Linux 更新链路 E2E（平台开发硬性验证，见 AGENTS.md 验证指南）。

用法：
  uv run python scripts/e2e_linux_update.py

前置：Rust 工具链（cargo）与 pnpm 可用；脚本自身持有全局验证锁，内部串行执行。
覆盖：
  1. Rust 检测/下载/签名单测（cargo test 过滤 linux_update + release_signature
     模块，含回退链、缓存、伪造签名、dev 通道序号等回归锚点）；
  2. 本机安装来源检测冒烟——调起 --ignored 用例 detect_current_machine_source
     打印 exe/source/arch 供人工核对（正确值随安装方式而变，不做断言）；
  3. 前端更新契约测试（vitest：更新组件 / 通道状态 / 资产定位 / 安装策略）。

输出：逐项 PASS/FAIL 与汇总；任一 FAIL 退出码非零。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TAURI_DIR = REPO / "frontend" / "src-tauri"
FRONTEND_DIR = REPO / "frontend"

# 前端更新契约测试（组件 / 通道状态 / 资产定位 / 安装与跳过策略）
FRONTEND_UPDATE_TESTS = [
    "src/components/update/__tests__/UpdateDialog.test.tsx",
    "src/components/update/__tests__/NativeUpdateShell.test.tsx",
    "src/components/update/__tests__/ReleaseNotesMarkdown.test.tsx",
    "src/hooks/__tests__/updateDialogPolicy.test.ts",
    "src/hooks/__tests__/updateSkipVersion.test.ts",
    "src/hooks/__tests__/useAutoUpdate.test.ts",
    "src/hooks/__tests__/useAutoUpdateManual.test.tsx",
    "src/hooks/__tests__/useAutoUpdateSource.test.ts",
    "src/utils/__tests__/linuxUpdateAssets.test.ts",
    "src/utils/__tests__/updateChannel.test.ts",
]

_results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, note: str = "") -> None:
    _results.append((name, ok, note))
    suffix = f" — {note}" if note else ""
    print(f"  {'PASS' if ok else 'FAIL'}: {name}{suffix}")


def find_pnpm() -> str | None:
    """Windows 上 npm 全局装的是 pnpm.cmd；无后缀的 sh 脚本 CreateProcess 起不来。"""
    if os.name == "nt":
        return shutil.which("pnpm.cmd") or shutil.which("pnpm")
    return shutil.which("pnpm")


def run_step(title: str, argv: list[str], cwd: Path) -> None:
    print(f"\n===== {title} =====")
    env = {**os.environ, "CARGO_BUILD_JOBS": "1"}
    try:
        proc = subprocess.run(argv, cwd=cwd, env=env)
    except OSError as exc:
        record(title, False, f"无法启动 {argv[0]}：{exc}")
        return
    record(title, proc.returncode == 0)


def main() -> int:
    cargo = shutil.which("cargo")
    if not cargo:
        print(
            "错误：未找到 cargo——Rust 侧用例需要 Rust 工具链（rustup）。安装后重跑本脚本。",
            file=sys.stderr,
        )
        return 1

    manifest = str(TAURI_DIR / "Cargo.toml")

    # 1. Rust 检测/下载/签名单测
    run_step(
        "Rust 检测/下载/签名单测",
        [cargo, "test", "--manifest-path", manifest, "--", "linux_update", "release_signature"],
        REPO,
    )

    # 2. 本机安装来源检测冒烟（人工核对输出；非 Linux 宿主输出 unknown 属预期）
    run_step(
        "本机安装来源检测冒烟（人工核对输出）",
        [
            cargo,
            "test",
            "--manifest-path",
            manifest,
            "--",
            "detect_current_machine_source",
            "--ignored",
            "--nocapture",
        ],
        REPO,
    )

    # 3. 前端更新契约测试（vitest 单 worker，遵守仓库串行验证规矩）
    pnpm = find_pnpm()
    if not pnpm:
        print("错误：未找到 pnpm——前端契约段无法执行。", file=sys.stderr)
        record("前端更新契约测试", False, "pnpm 不可用")
    else:
        run_step(
            "前端更新契约测试",
            [
                pnpm,
                "test",
                *FRONTEND_UPDATE_TESTS,
                "--maxWorkers=1",
                "--no-file-parallelism",
                "--maxConcurrency=1",
            ],
            FRONTEND_DIR,
        )

    fails = [r for r in _results if not r[1]]
    print(f"\n===== E2E 汇总：{len(_results) - len(fails)}/{len(_results)} PASS =====")
    for name, _, note in fails:
        print(f"  FAIL: {name} {note}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from run_validation import validation_slot

    with validation_slot():
        sys.exit(main())
