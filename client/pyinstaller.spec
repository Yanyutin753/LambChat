# -*- mode: python ; coding: utf-8 -*-
"""lambchat_sandbox daemon 的 PyInstaller 打包 spec（onefile 单文件产物）。

入口 client/lambchat_sandbox/__main__.py 与 ``python -m lambchat_sandbox`` 等价；
包内运行路径依赖 stdlib + httpx；computer-use 后端按平台经 ``cua`` 依赖组
注入（macOS atomacos→PyObjC / Windows pywinauto / Linux dogtail + pyautogui），
均为 cua_* op 的懒加载 import——Analysis 按入口可达性自动收集，未同步 cua 组
的构建只会让 cua op 报 unsupported_platform，不影响其余链路。

路径基准：PyInstaller 执行 spec 时不切换 cwd，spec 内相对路径会随调用目录漂移，
因此统一用内置 ``SPECPATH``（spec 所在目录 client/）反推仓库根，
保证从任意 cwd（Makefile / 脚本 / CI）调用都稳定。

瘦身 excludes（xref 实测，2026-09）：dev venv 里 httpx[cli] 的可选链会拖进
rich→pygments→PIL→numpy→yaml、click、zstandard，anyio 拖进 uvloop/_pytest，
全部是条件导入（运行时才 import、缺失即降级），daemon 的运行路径不触发；
不排除时 onefile 产物 50MB（未压缩 139.6MB，numpy+zstandard+uvloop+pillow 占 104MB）。
psutil 不在此列：procsup.py（Windows 父进程监视）模块级硬依赖，排除即崩。
"""

from pathlib import Path
import sys

LINUX_SYSTEM_PACKAGES = ["/usr/lib/python3/dist-packages"] if sys.platform.startswith("linux") else []
sys.path.extend(LINUX_SYSTEM_PACKAGES)

REPO_ROOT = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(REPO_ROOT / "client/lambchat_sandbox/__main__.py")],
    pathex=[str(REPO_ROOT / "client"), *LINUX_SYSTEM_PACKAGES],
    binaries=[],
    datas=[],
    hiddenimports=[
        # computer-use 事件/截屏链:pyautogui 懒加载这些模块(函数体内
        # import / try-import),静态分析抓不到;2026-10-08 生产实测
        # Windows daemon 截屏全灭(pyscreeze 缺)即此因。pyperclip 是
        # 非 ASCII 输入的剪贴板路径(中文输入全靠它)。
        "pyscreeze",
        "PIL",
        "pyperclip",
        "pyautogui",
        *(["pyatspi", "gi.repository.Atspi"] if LINUX_SYSTEM_PACKAGES else []),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # httpx[cli] 可选链（rich→pygments→PIL→numpy→yaml、click、zstandard）。
        # psutil 曾误列于此（当作 rich 链传递依赖），实为 procsup.py 硬依赖。
        # PIL 已从排除名单移出:computer-use 截屏(pyscreeze)硬依赖。
        "rich",
        "pygments",
        "markdown_it",
        "numpy",
        "yaml",
        "click",
        "zstandard",
        # anyio 可选事件循环与 pytest 插件
        "uvloop",
        "_pytest",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="lambchat-daemon",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    # macOS：强制 ad-hoc 签名**全部内嵌二进制**（dylib/so/可执行逐个，构建期
    # 落印、随归档分发）。默认 None 时 PyInstaller 按宿主/目标架构启发式决定
    # 是否签名（x86_64 目标在 arm64 宿主上跳过），未签名的 libpython3.12.dylib
    # 解包后 dlopen 即被 arm64 内核/AMFI SIGKILL——v2.9.2 macOS「daemon 起不
    # 来」的第一失败点（临时副本实验证实：解包目录里的内嵌库缺有效签名）。
    # ad-hoc（'-'）与发布链路的 tauri signingIdentity "-" 同语义，无需证书。
    codesign_identity="-" if __import__("sys").platform == "darwin" else None,
    entitlements_file=None,
)
